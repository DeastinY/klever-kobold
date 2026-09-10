#!/usr/bin/env python3
"""Recall@k measured through the shipped runtime, with and without reranking.

eval/retrieval_eval.py measures the lab implementation. This measures the program
users run -- Ollama embeddings, float16 index, the real fusion -- so a retrieval
change can be checked at the operating point before spending a full end-to-end
answer run on it.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import sys
import time

import orjson

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", type=pathlib.Path, default=ROOT / "eval" / "holdout.jsonl")
    ap.add_argument("--index", type=pathlib.Path, default=ROOT / "dist" / "kobold-index")
    ap.add_argument("-k", type=int, default=8)
    ap.add_argument("--pool", type=int, default=24)
    ap.add_argument("--rerank", action="store_true")
    args = ap.parse_args()

    from kleverkobold.app import Assistant

    a = Assistant(args.index)
    canon = a.index.canonical
    items = [orjson.loads(l) for l in args.benchmark.open("rb")
             if orjson.loads(l)["source_ids"] and not orjson.loads(l).get("excluded")]

    def partners(pos: set[int]) -> set[int]:
        out = set(pos)
        for p in pos:
            m = a.index.meta[p]
            for field in ("remaster_id", "legacy_id"):
                for t in (m.get(field) or []):
                    q = a.index.position(f"aon:{m['category']}:{t}")
                    if q is not None:
                        out.add(q)
        return out

    hits = 0
    by_family: dict[str, list[int]] = collections.defaultdict(list)
    started = time.time()
    for n, item in enumerate(items, 1):
        gold_pos = {p for p in (a.index.position(g) for g in item["source_ids"]) if p is not None}
        gold = {canon[p] for p in partners(gold_pos)}
        found = a.search(item["question"], k=args.k, rerank=args.rerank, pool=args.pool)
        got = {canon[a.index.position(h.chunk_id)] for h in found}
        ok = bool(gold & got)
        hits += ok
        by_family[item["family"]].append(int(ok))
        if n % 40 == 0:
            print(f"  {n}/{len(items)}", flush=True)

    label = f"rerank pool={args.pool}" if args.rerank else "fusion only"
    print(f"\n{args.benchmark.name}  {label}  k={args.k}")
    print(f"  recall@{args.k}: {hits}/{len(items)} = {hits / len(items):.1%}"
          f"   ({time.time() - started:.0f}s)")
    for fam, vals in sorted(by_family.items()):
        print(f"    {fam:18s} n={len(vals):4d}  {sum(vals) / len(vals):6.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
