#!/usr/bin/env python3
"""Trivial-strategy scores, so a model's number can be read against something.

A benchmark family is only informative above its dumbest strategy.  "What is the
rarity of X?" looks like a real question until you notice that answering
"uncommon" every time scores 70%.  This prints, per family, what a model that
knows nothing about Pathfinder can get.
"""

from __future__ import annotations

import argparse
import collections
import pathlib

import orjson

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", type=pathlib.Path, default=ROOT / "eval" / "benchmark.jsonl")
    args = ap.parse_args()
    items = [orjson.loads(line) for line in args.benchmark.open("rb")]

    by_family = collections.defaultdict(list)
    for it in items:
        by_family[it["family"]].append(it)

    print(f"{'family':18s} {'n':>4s} {'majority':>9s}  best constant answer")
    print(f"{'-' * 18} {'-' * 4} {'-' * 9}  {'-' * 40}")
    for fam in sorted(by_family):
        rows = by_family[fam]
        n = len(rows)
        if rows[0]["answer_type"] in ("int", "exact"):
            counts = collections.Counter(r["answer"] for r in rows)
            answer, hits = counts.most_common(1)[0]
            print(f"{fam:18s} {n:4d} {hits / n:8.1%}  {answer!r}")
        elif rows[0]["answer_type"] == "abstain":
            print(f"{fam:18s} {n:4d} {1.0:8.1%}  always refuse (so pair it with the other families)")
        elif rows[0]["answer_type"] == "set":
            print(f"{fam:18s} {n:4d} {0.0:8.1%}  no constant set matches; graded on recall and over-answering")
        else:
            print(f"{fam:18s} {n:4d} {1.0:8.1%}  say nothing at all (contamination is a negative check)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
