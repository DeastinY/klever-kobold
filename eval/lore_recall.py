#!/usr/bin/env python3
"""Lore recall through the shipped runtime, and the promise that rules stay rules.

Runs the hand-written lore holdout (``eval/seeds/lore_holdout.jsonl``) through
``Assistant.retrieve`` at the operating point -- eight excerpts, reranked,
scope ``auto`` -- and reports:

* **recall@8 on lore questions**: an expected wiki page (or any section of it)
  is among the eight;
* **scope on the rules controls**: how many were sent to lore, and whether any
  wiki row reached their excerpts. The second number must be zero: that is the
  guarantee the scope exists to keep.

A lore question is graded on page names, not text: "Cheliax › Government"
counts for "Cheliax". Sections are cited by anchor, so the page is one click
away either way.

    python eval/lore_recall.py --index dist/kobold-index
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kleverkobold.app import DEFAULT_K, Assistant  # noqa: E402


def page_of(name: str) -> str:
    return name.split(" › ")[0].strip().lower()


def found(expect: list[str], hits) -> str | None:
    want = {e.lower() for e in expect}
    for h in hits:
        if h.lore and page_of(h.name) in want:
            return h.name
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=pathlib.Path, default=ROOT / "eval" / "seeds" / "lore_holdout.jsonl")
    ap.add_argument("--index", type=pathlib.Path, default=ROOT / "dist" / "kobold-index")
    ap.add_argument("--ollama", default="http://localhost:11434")
    ap.add_argument("--llm-model", default=None)
    ap.add_argument("-k", type=int, default=DEFAULT_K)
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--scope", default="auto", choices=("auto", "rules", "lore"))
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "eval" / "runs" / "lore_recall")
    args = ap.parse_args()

    a = Assistant(args.index, args.ollama, llm_model=args.llm_model)
    if not a.has_lore:
        print(f"{args.index} carries no lore; nothing to measure")
        return 1
    items = [json.loads(line) for line in args.seeds.open()]
    rows, started = [], time.time()
    for n, it in enumerate(items, 1):
        plan, hits, timings = a.retrieve(it["question"], k=args.k, rerank=not args.no_rerank,
                                         scope=args.scope)
        # The wider pool, before the rerank cut, says whether a miss is the
        # retriever's or the reranker's.
        pool = a.search(it["question"], k=24, plan=plan, rerank=False, pool=24, scope=args.scope)
        rows.append({
            **it, "scope": "lore" if plan.get("lore") else "rules",
            "hits": [{"name": h.name, "corpus": h.corpus} for h in hits],
            "hit": found(it["expect"], hits), "in_pool": found(it["expect"], pool),
            "lore_hits": sum(1 for h in hits if h.lore),
            "timings": timings,
        })
        if n % 10 == 0:
            print(f"  {n}/{len(items)}  {time.time() - started:.0f}s", flush=True)

    lore = [r for r in rows if r["family"] == "lore"]
    ctrl = [r for r in rows if r["family"] == "rules-control"]
    scores = {
        "index": str(args.index), "model": a.manifest["ollama_llm"], "scope": args.scope,
        "k": args.k, "rerank": not args.no_rerank,
        "lore": {"n": len(lore),
                 "sent_to_lore": sum(r["scope"] == "lore" for r in lore),
                 f"recall@{args.k}": sum(bool(r["hit"]) for r in lore),
                 "recall@24_pool": sum(bool(r["in_pool"]) for r in lore)},
        "rules_controls": {"n": len(ctrl),
                           "sent_to_lore": sum(r["scope"] == "lore" for r in ctrl),
                           "with_a_lore_excerpt": sum(r["lore_hits"] > 0 for r in ctrl)},
        "mean_seconds": {key: round(sum(r["timings"].get(key, 0) for r in rows) / len(rows), 2)
                         for key in ("rewrite", "retrieve", "rerank")},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.with_suffix(".jsonl").open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    args.out.with_suffix(".scores.json").write_text(json.dumps(scores, indent=2))
    print(json.dumps(scores, indent=2))

    print("\nlore misses:")
    for r in lore:
        if not r["hit"]:
            where = ("in pool, cut by rerank" if r["in_pool"]
                     else "sent to rules" if r["scope"] == "rules" else "not retrieved")
            print(f"  {r['question']!r} -> {where}; got " + ", ".join(h["name"] for h in r["hits"][:4]))
    print("\nrules controls that saw lore:")
    for r in ctrl:
        if r["lore_hits"] or r["scope"] == "lore":
            print(f"  {r['question']!r}: scope={r['scope']} lore excerpts={r['lore_hits']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
