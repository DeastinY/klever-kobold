"""Bulk export of the Archives of Nethys corpus.

AoN serves its public search index from an anonymously-readable Elasticsearch
cluster.  Every document carries a pre-rendered ``markdown`` field, which is
the cleanest PF2e rules text available anywhere -- structured, link-annotated,
and already split one-document-per-game-entity.

Anonymous access is read-only and does not permit ``_search/scroll`` or PIT, so
we paginate per category with ``from``/``size``.  Every category is well under
Elasticsearch's 10k deep-paging window (largest is ``equipment`` at ~9.1k), so
this is safe.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import orjson

ES_URL = "https://elasticsearch.aonprd.com"
INDEX = "aon"
PAGE_SIZE = 500


@dataclass(frozen=True)
class Category:
    name: str
    count: int


def _post(client: httpx.Client, path: str, body: dict) -> dict:
    for attempt in range(5):
        try:
            r = client.post(f"{ES_URL}{path}", json=body, timeout=60.0)
            r.raise_for_status()
            return orjson.loads(r.content)
        except (httpx.HTTPError, orjson.JSONDecodeError):
            if attempt == 4:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def total_documents(client: httpx.Client) -> int:
    r = client.get(f"{ES_URL}/{INDEX}/_count", timeout=30.0)
    r.raise_for_status()
    return orjson.loads(r.content)["count"]


def categories(client: httpx.Client) -> list[Category]:
    body = {"size": 0, "aggs": {"cats": {"terms": {"field": "category", "size": 200}}}}
    res = _post(client, f"/{INDEX}/_search", body)
    buckets = res["aggregations"]["cats"]["buckets"]
    return [Category(b["key"], b["doc_count"]) for b in buckets]


def fetch_category(client: httpx.Client, category: str) -> Iterator[dict]:
    """Yield every ``_source`` document in a category, in index order."""
    offset = 0
    while True:
        body = {
            "from": offset,
            "size": PAGE_SIZE,
            "query": {"term": {"category": category}},
            "sort": ["_doc"],
        }
        hits = _post(client, f"/{INDEX}/_search", body)["hits"]["hits"]
        if not hits:
            return
        for hit in hits:
            doc = hit["_source"]
            doc.setdefault("_es_id", hit["_id"])
            yield doc
        offset += len(hits)
        if len(hits) < PAGE_SIZE:
            return
