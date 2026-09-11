#!/usr/bin/env python3
"""Resolve the hand-written natural holdout into a scoreable benchmark file.

The generated benchmark asks questions the way its generator writes them: 87.7%
of its retrieval items name the target entity verbatim, and BM25 alone gets 88.5%
R@5 on it. That is a keyed lookup, not a question, and it is not how anyone at a
table talks. Every headline number so far rests on that distribution.

This holdout is written by hand in player language -- describing a feat instead of
naming it, asking what to do in a situation, comparing two options, asking with
pre-Remaster vocabulary, and asking about things that do not exist. Entities are
referenced by (category, name) and resolved to chunk ids here, so the file
survives a corpus rebuild.

The entities are drawn from the generated benchmark's own pool, which the LoRA's
training data explicitly excluded. So a drop here isolates *phrasing*: same
corpus, same exclusions, different words.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import sys

import orjson

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=pathlib.Path,
                    default=ROOT / "eval" / "seeds" / "natural_holdout.jsonl")
    ap.add_argument("--chunks", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "aon_chunks.jsonl")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "eval" / "holdout.jsonl")
    args = ap.parse_args()

    rows = [orjson.loads(line) for line in args.chunks.open("rb")]
    # Prefer the current entry when a name exists in both Remaster and legacy form.
    index: dict[tuple[str, str], dict] = {}
    for r in rows:
        if not r["name"]:
            continue
        key = (r["category"], r["name"].lower())
        keep = index.get(key)
        if keep is None or (keep["remaster_status"] == "legacy" != r["remaster_status"]):
            index[key] = r

    items, unresolved = [], []
    for n, line in enumerate(args.seed.open("rb")):
        seed = orjson.loads(line)
        source_ids, source_urls = [], []
        for category, name in seed.get("refs") or []:
            hit = index.get((category, name.lower()))
            if not hit:
                unresolved.append((category, name))
                continue
            source_ids.append(hit["id"])
            source_urls.append(hit["url"])
        item = {
            "id": f"{seed['family']}-{n:03d}",
            "family": seed["family"],
            "question": seed["question"],
            "answer": seed["answer"],
            "answer_type": seed["answer_type"],
            "acceptable": seed.get("acceptable", []),
            "must_contain": seed.get("must_contain", []),
            "must_not_contain": seed.get("must_not_contain", []),
            "source_ids": source_ids,
            "source_urls": source_urls,
        }
        items.append(item)

    if unresolved:
        print("UNRESOLVED refs (fix the seed):", file=sys.stderr)
        for category, name in unresolved:
            print(f"  {category}/{name}", file=sys.stderr)
        return 1

    with args.out.open("wb") as fh:
        for item in items:
            fh.write(orjson.dumps(item))
            fh.write(b"\n")

    fams = collections.Counter(i["family"] for i in items)
    print(f"wrote {len(items)} items -> {args.out}")
    for f, c in fams.most_common():
        print(f"  {f:20s} {c:3d}")
    with_gold = sum(1 for i in items if i["source_ids"])
    verbatim = sum(1 for i in items if i["source_ids"] and names_target(i, index))
    print(f"  {with_gold} carry a gold chunk; {verbatim} name it verbatim "
          f"({verbatim / with_gold:.0%}) — the generated benchmark's figure is 88%")
    return 0


def names_target(item: dict, index: dict) -> bool:
    by_id = {r["id"]: r for r in index.values()}
    for sid in item["source_ids"]:
        row = by_id.get(sid)
        if row and row["name"] and row["name"].lower() in item["question"].lower():
            return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
