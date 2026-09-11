#!/usr/bin/env python3
"""Does the rewriter send lore questions to lore and nothing else there?

Two things are measured, because the lore prompt is the rules prompt plus one
line and the rules path is what every published number rests on:

1. **Scope.** On the hand-written lore holdout (should say lore), its rules
   controls (should say rules), and the generated benchmark (all rules). The
   number that matters is the rules side: a rules question sent to lore gets a
   wiki paragraph among its excerpts, which is the failure this exists to stop.
2. **Drift.** SUMMARY and KINDS from the old prompt against the new one on the
   same questions. If adding SCOPE changed what the rewriter writes, the
   holdout has to be re-run before this ships; if it did not, the recall
   numbers carry over.

No index is needed: this talks to the model alone.

    python eval/scope_probe.py                 # 4B, all 459 benchmark items
    python eval/scope_probe.py --limit 100 --llm-model qwen3.5:9b
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kleverkobold.app import (  # noqa: E402
    DEFAULT_LLM,
    REWRITE_SCOPE_SYSTEM,
    REWRITE_SYSTEM,
    Ollama,
    parse_plan,
)


def jaccard(a, b) -> float:
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 1.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=pathlib.Path, default=ROOT / "eval" / "seeds" / "lore_holdout.jsonl")
    ap.add_argument("--benchmark", type=pathlib.Path, default=ROOT / "eval" / "benchmark.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="benchmark items to probe (0 = all)")
    ap.add_argument("--llm-model", default=DEFAULT_LLM)
    ap.add_argument("--ollama", default="http://localhost:11434")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "eval" / "runs" / "scope_probe")
    args = ap.parse_args()

    items = [json.loads(line) for line in args.seeds.open()]
    bench = [json.loads(line) for line in args.benchmark.open()]
    if args.limit:
        random.Random(args.seed).shuffle(bench)
        bench = bench[:args.limit]
    items += [{"id": b["id"], "family": "benchmark:" + b.get("family", "?"),
               "question": b["question"], "expect": []} for b in bench]

    client = Ollama(args.ollama)
    rows, started = [], time.time()
    for n, it in enumerate(items, 1):
        old = parse_plan(client.chat(REWRITE_SYSTEM, f"Question: {it['question']}",
                                     args.llm_model, max_tokens=90))
        new = parse_plan(client.chat(REWRITE_SCOPE_SYSTEM, f"Question: {it['question']}",
                                     args.llm_model, max_tokens=100))
        rows.append({**it, "old": old, "new": new})
        if n % 50 == 0:
            print(f"  {n}/{len(items)}  {time.time() - started:.0f}s", flush=True)

    want = lambda it: "lore" if it["family"] == "lore" else "rules"  # noqa: E731
    by_family = collections.defaultdict(lambda: {"n": 0, "right": 0})
    for r in rows:
        fam = r["family"].split(":")[0]
        by_family[fam]["n"] += 1
        by_family[fam]["right"] += r["new"]["scope"] == want(r)
    # Drift is measured on the rules questions only: the lore ones are meant to
    # come out different (KINDS: none), and would flatter nothing by agreeing.
    rules_rows = [r for r in rows if want(r) == "rules"]
    kinds_same = sum(r["old"]["categories"] == r["new"]["categories"] for r in rules_rows)
    kinds_jac = sum(jaccard(r["old"]["categories"], r["new"]["categories"]) for r in rules_rows) / len(rules_rows)
    summ_jac = sum(jaccard(r["old"]["summary"].lower().split(),
                           r["new"]["summary"].lower().split()) for r in rules_rows) / len(rules_rows)
    empty_old = sum(not r["old"]["summary"] for r in rules_rows)
    empty_new = sum(not r["new"]["summary"] for r in rules_rows)

    scores = {
        "model": args.llm_model, "items": len(rows),
        "scope": {fam: {"n": v["n"], "right": v["right"], "acc": round(v["right"] / v["n"], 3)}
                  for fam, v in by_family.items()},
        "rules_sent_to_lore": sum(1 for r in rows if want(r) == "rules" and r["new"]["scope"] == "lore"),
        "drift": {"on": "rules questions only", "n": len(rules_rows),
                  "kinds_identical": round(kinds_same / len(rules_rows), 3),
                  "kinds_jaccard": round(kinds_jac, 3),
                  "summary_token_jaccard": round(summ_jac, 3),
                  "empty_summary_old": empty_old, "empty_summary_new": empty_new},
        "seconds": round(time.time() - started),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.with_suffix(".jsonl").open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    args.out.with_suffix(".scores.json").write_text(json.dumps(scores, indent=2))

    print(json.dumps(scores, indent=2))
    print("\nrules questions sent to lore:")
    for r in rows:
        if want(r) == "rules" and r["new"]["scope"] == "lore":
            print(f"  [{r['family']}] {r['question']}")
    print("\nlore questions sent to rules:")
    for r in rows:
        if want(r) == "lore" and r["new"]["scope"] == "rules":
            print(f"  {r['question']}")
    print("\nkinds that changed (first 15):")
    shown = 0
    for r in rules_rows:
        if r["old"]["categories"] != r["new"]["categories"] and shown < 15:
            print(f"  {r['question'][:70]!r}: {r['old']['categories']} -> {r['new']['categories']}")
            shown += 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
