#!/usr/bin/env python3
"""Mine real Pathfinder 2e questions, with labels derived from human answers.

Both existing benchmarks were written by the thing being measured. The generated
one names its target entity in 88% of questions because its generator did; the
hand-written one is better, but it is still 109 questions written by one author
in one sitting, and it shares that author's blind spots by construction.

RPG StackExchange has thousands of Pathfinder 2e questions asked by people trying
to run a game, with accepted answers written by other people. That gives two
things nothing here has had before:

* **Questions nobody involved in this project phrased.**
* **Labels that do not come from this project's retriever.** 397 of 574 accepted
  answers *link to Archives of Nethys directly*, and those URLs are the same ones
  the corpus carries. When a human answers "see the Escape action and the grabbed
  condition" and links both pages, those two chunks are what retrieval should
  surface -- an exact label, chosen by a person, with no matching heuristic in
  between.

An earlier version matched entry *names* against the answer prose and produced
labels like "Advanced Player's Guide, Treasure by Level" for a question about
weapon runes, and "Combination, Language" for a question about pronunciation.
Name matching in free text is too noisy to be a benchmark. Links are not.
"""

from __future__ import annotations

import argparse
import collections
import html
import pathlib
import re
import sys
import time

import httpx
import orjson

ROOT = pathlib.Path(__file__).resolve().parents[1]
API = "https://api.stackexchange.com/2.3/questions"

RE_TAG = re.compile(r"<[^>]+>")
RE_WS = re.compile(r"\s+")
RE_AON = re.compile(r'https?://(?:2e\.)?aonprd\.com/[^"\s<>\)\]]+', re.I)
# Pages that are not entries: site search, book listings, the front page.
RE_NOT_ENTRY = re.compile(r"/(?:Search|Sources|Default|Licenses)\.aspx", re.I)


def normalise_url(url: str) -> str:
    """Reduce an AoN link to page + numeric id.

    Answers link with tracking fragments, HTML-escaped ampersands and
    &Redirected=1, all of which name the same entry.
    """
    url = html.unescape(url).split("#")[0]
    match = re.search(r"/([A-Za-z]+)\.aspx\?ID=(\d+)", url)
    if not match:
        return ""
    return f"{match.group(1).lower()}:{match.group(2)}"

# Entry names that are also ordinary English. Matching these produces noise, not
# labels: an answer saying "you take a reaction" is not citing the Shield spell.
COMMON = {
    "shield", "fear", "sleep", "heal", "harm", "message", "light", "darkness",
    "grease", "fly", "jump", "hide", "seek", "sneak", "climb", "swim", "trip",
    "grapple", "escape", "shove", "disarm", "lie", "track", "subsist", "search",
    "stand", "step", "stride", "strike", "release", "interact", "delay", "aid",
    "point out", "sustain", "dismiss", "crawl", "leap", "burrow", "arrest a fall",
    "avert gaze", "take cover", "raise a shield", "ready", "mount", "drop prone",
    "sense motive", "recall knowledge", "treat wounds", "administer first aid",
    "identify magic", "repair", "craft", "earn income", "learn a spell", "borrow an arcane spell",
    "coerce", "demoralize", "feint", "impersonate", "make an impression", "request",
    "tumble through", "balance", "squeeze", "force open", "high jump", "long jump",
    "disable a device", "pick a lock", "palm an object", "steal", "conceal an object",
    "perform", "gather information", "decipher writing",
}


def strip_html(text: str) -> str:
    return RE_WS.sub(" ", html.unescape(RE_TAG.sub(" ", text or ""))).strip()


def fetch(client: httpx.Client, tag: str, sort: str, pages: int, key: str | None) -> list[dict]:
    out: list[dict] = []
    for page in range(1, pages + 1):
        params = {
            "order": "desc", "sort": sort, "tagged": tag, "site": "rpg",
            "pagesize": 100, "page": page,
            # withbody gives question and answer text; we need the accepted answer.
            "filter": "withbody",
        }
        if key:
            params["key"] = key
        r = client.get(API, params=params, timeout=60.0)
        if r.status_code != 200:
            print(f"  page {page}: HTTP {r.status_code}", file=sys.stderr)
            break
        data = orjson.loads(r.content)
        out.extend(data.get("items", []))
        if not data.get("has_more"):
            break
        if data.get("backoff"):
            time.sleep(data["backoff"])
        time.sleep(0.4)
    return out


def fetch_answers(client: httpx.Client, ids: list[int]) -> dict[int, str]:
    """Accepted answers, fetched by id.

    The questions endpoint will not return answer bodies at any filter this API
    exposes without an app key, so they are fetched separately in batches of 100.
    """
    out: dict[int, str] = {}
    for start in range(0, len(ids), 100):
        batch = ids[start:start + 100]
        r = client.get(f"https://api.stackexchange.com/2.3/answers/{';'.join(map(str, batch))}",
                       params={"site": "rpg", "filter": "withbody", "pagesize": 100},
                       timeout=60.0)
        if r.status_code != 200:
            print(f"  answers batch: HTTP {r.status_code}", file=sys.stderr)
            break
        data = orjson.loads(r.content)
        for a in data.get("items", []):
            out[a["answer_id"]] = a.get("body", "")
        if data.get("backoff"):
            time.sleep(data["backoff"])
        time.sleep(0.4)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "aon_chunks.jsonl")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "eval" / "wild.jsonl")
    ap.add_argument("--raw", type=pathlib.Path,
                    default=ROOT / "data" / "raw" / "stackexchange_pf2e.json")
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument("--max-entities", type=int, default=4)
    ap.add_argument("--min-name-len", type=int, default=5)
    args = ap.parse_args()

    rows = [orjson.loads(l) for l in args.chunks.open("rb")]

    # Only categories that answer a rules question. Source books, category pages
    # and article stubs match constantly and cite nothing: the first run labelled
    # "Can bombs gain weapon runes?" with "Advanced Player's Guide, Treasure by
    # Level", which is a bibliography, not an answer.
    USEFUL = {"feat", "spell", "action", "condition", "equipment", "weapon", "armor",
              "shield", "creature", "hazard", "trait", "class-feature", "ritual",
              "archetype", "background", "heritage", "ancestry", "class", "skill",
              "deity", "relic", "curse", "disease", "familiar-ability", "rules"}

    by_name: dict[str, dict] = {}
    for r in rows:
        if not r["name"] or r["category"] not in USEFUL:
            continue
        # Section headings are entries too ("Step 1: Roll the Damage Dice and
        # Apply Modifiers"). They are never what a human cites by name.
        if len(r["name"]) > 40 or ":" in r["name"]:
            continue
        key = r["name"].lower()
        keep = by_name.get(key)
        if keep is None or (keep["remaster_status"] == "legacy" != r["remaster_status"]):
            by_name[key] = r

    # url -> chunk, for exact matching against the links humans cited.
    by_url: dict[str, dict] = {}
    for r in rows:
        if r.get("url") and r["category"] in USEFUL:
            key = normalise_url(r["url"])
            keep = by_url.get(key)
            if keep is None or (keep["remaster_status"] == "legacy" != r["remaster_status"]):
                by_url[key] = r
    print(f"{len(by_url):,} corpus entries addressable by URL")

    args.raw.parent.mkdir(parents=True, exist_ok=True)
    if args.raw.exists():
        questions = orjson.loads(args.raw.read_bytes())
        print(f"reusing {len(questions)} cached questions from {args.raw}")
    else:
        with httpx.Client(headers={"Accept-Encoding": "gzip"}) as client:
            questions = []
            for sort in ("votes", "activity"):
                got = fetch(client, "pathfinder-2e", sort, args.pages, None)
                print(f"  {sort}: {len(got)}")
                questions.extend(got)
        seen = set()
        questions = [q for q in questions
                     if not (q["question_id"] in seen or seen.add(q["question_id"]))]
        args.raw.write_bytes(orjson.dumps(questions))
        print(f"fetched {len(questions)} unique questions -> {args.raw}")

    answers_path = args.raw.with_name(args.raw.stem + "_answers.json")
    accepted_ids = [q["accepted_answer_id"] for q in questions if "accepted_answer_id" in q]
    if answers_path.exists():
        answers = {int(k): v for k, v in orjson.loads(answers_path.read_bytes()).items()}
    else:
        with httpx.Client(headers={"Accept-Encoding": "gzip"}) as client:
            answers = fetch_answers(client, accepted_ids)
        answers_path.write_bytes(orjson.dumps({str(k): v for k, v in answers.items()}))
    print(f"{len(answers)} accepted answers of {len(accepted_ids)} requested")

    kept, stats = [], collections.Counter()
    for q in questions:
        if not q.get("is_answered") or "accepted_answer_id" not in q:
            stats["no accepted answer"] += 1
            continue
        answer_body = answers.get(q["accepted_answer_id"])
        if not answer_body:
            stats["accepted answer not returned"] += 1
            continue

        title = strip_html(q["title"])
        body = strip_html(q.get("body", ""))[:600]
        answer_text = strip_html(answer_body)
        if len(answer_text) < 120:
            stats["answer too short"] += 1
            continue

        links = {normalise_url(u) for u in RE_AON.findall(answer_body)
                 if not RE_NOT_ENTRY.search(u)}
        cited = [by_url[u] for u in sorted(links) if u in by_url]
        if not 1 <= len(cited) <= args.max_entities:
            stats["no AoN links" if not links else
                  ("links resolved to nothing" if not cited else "too many entities")] += 1
            continue

        entries = cited
        kept.append({
            "id": f"wild-{q['question_id']}",
            "family": "wild_rules",
            "question": title,
            "detail": body[:400],
            "answer": answer_text[:600],
            "answer_type": "free",
            "acceptable": [],
            "must_contain": [],
            "must_not_contain": [],
            "source_ids": [e["id"] for e in entries],
            "source_urls": [e["url"] for e in entries],
            "cited_entities": [e["name"] for e in entries],
            "score": q.get("score", 0),
            "link": q.get("link"),
        })

    kept.sort(key=lambda k: -k["score"])
    with args.out.open("wb") as fh:
        for item in kept:
            fh.write(orjson.dumps(item))
            fh.write(b"\n")

    print(f"\nkept {len(kept)} questions with human-derived labels -> {args.out}")
    for k, v in stats.most_common():
        print(f"  dropped: {k:32s} {v}")
    print("\nexamples:")
    for item in kept[:6]:
        print(f"  [{item['score']:3d}] {item['question'][:74]}")
        print(f"        cited: {', '.join(item['cited_entities'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
