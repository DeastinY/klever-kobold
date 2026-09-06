"""Bulk export of PathfinderWiki (Golarion lore) via the MediaWiki API.

We pull raw wikitext rather than rendered extracts: the ``{{Person}}`` /
``{{City}}`` / ``{{Deity}}`` infoboxes carry structured lore (homeland, ancestry,
deity domains, region) that the plain-text extract API discards, and that
structure is exactly what makes good synthetic QA pairs later.

PathfinderWiki content is published under Paizo's Community Use Policy:
non-commercial, freely-available use only.  See docs/LICENSING.md.
"""

from __future__ import annotations

import time
from typing import Iterator

import httpx
import orjson

API = "https://pathfinderwiki.com/w/api.php"
UA = "pf2etune/0.1 (personal research corpus; contact via github)"
BATCH = 50
DELAY = 0.25  # be a polite guest on a volunteer-run wiki


def _get(client: httpx.Client, params: dict) -> dict:
    params = {**params, "format": "json", "formatversion": "2"}
    for attempt in range(5):
        try:
            r = client.get(API, params=params, timeout=60.0)
            r.raise_for_status()
            return orjson.loads(r.content)
        except (httpx.HTTPError, orjson.JSONDecodeError):
            if attempt == 4:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def site_info(client: httpx.Client) -> dict:
    res = _get(client, {"action": "query", "meta": "siteinfo", "siprop": "statistics|rightsinfo"})
    return res["query"]


def iter_pages(client: httpx.Client, namespace: int = 0) -> Iterator[dict]:
    """Yield ``{title, pageid, timestamp, wikitext}`` for every page in a namespace."""
    params = {
        "action": "query",
        "generator": "allpages",
        "gapnamespace": namespace,
        "gaplimit": BATCH,
        "gapfilterredir": "nonredirects",
        "prop": "revisions",
        "rvslots": "main",
        "rvprop": "content|timestamp|ids",
    }
    cont: dict = {}
    while True:
        res = _get(client, {**params, **cont})
        for page in res.get("query", {}).get("pages", []):
            revs = page.get("revisions")
            if not revs:
                continue
            main = revs[0].get("slots", {}).get("main", {})
            if "content" not in main:
                continue
            yield {
                "title": page["title"],
                "pageid": page["pageid"],
                "revid": revs[0].get("revid"),
                "timestamp": revs[0].get("timestamp"),
                "wikitext": main["content"],
            }
        if "continue" not in res:
            return
        cont = res["continue"]
        time.sleep(DELAY)
