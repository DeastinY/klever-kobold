#!/usr/bin/env python3
"""Lore answers, end to end, graded by string match like everything else here.

``eval/seeds/lore_answers.jsonl`` is thirty hand-written Golarion questions
with one checkable fact each -- "Who rules Cheliax?" must name Abrogail. Each
expectation was verified to appear on the wiki page it names, so a miss is the
kobold's and not the seed's. The grade is the answer containing any of
``must_contain``, case-insensitive; also reported: whether the question was
sent to lore, and whether the Source line cites PathfinderWiki.

Thirty items is a smoke test with a name, not a benchmark: one item is 3.3%.

    python eval/lore_answers.py --index dist/kobold-index --llm-model qwen3.5:4b
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=pathlib.Path, default=ROOT / "eval" / "seeds" / "lore_answers.jsonl")
    ap.add_argument("--index", type=pathlib.Path, default=ROOT / "dist" / "kobold-index")
    ap.add_argument("--ollama", default="http://localhost:11434")
    ap.add_argument("--llm-model", default=None)
    ap.add_argument("-k", type=int, default=DEFAULT_K)
    ap.add_argument("--scope", default="auto", choices=("auto", "rules", "lore"))
    ap.add_argument("--label", default=None, help="run name; default lore_answers_<model>")
    args = ap.parse_args()

    a = Assistant(args.index, args.ollama, llm_model=args.llm_model)
    model = a.manifest["ollama_llm"]
    label = args.label or "lore_answers_" + model.replace(":", "-").replace("/", "-")
    items = [json.loads(l) for l in args.seeds.open()]
    rows, started = [], time.time()
    for it in items:
        out = a.ask(it["question"], k=args.k, scope=args.scope)
        answer = out["answer"]
        low = answer.lower()
        rows.append({
            **it, "answer": answer, "scope": out["scope"],
            "correct": any(m.lower() in low for m in it["must_contain"]),
            "cites_wiki": "pathfinderwiki.com" in low,
            "sources": [s["name"] for s in out["sources"]],
            "timings": out["timings"],
        })
    scores = {
        "model": model, "scope": args.scope, "k": args.k, "n": len(rows),
        "correct": sum(r["correct"] for r in rows),
        "sent_to_lore": sum(r["scope"] == "lore" for r in rows),
        "cites_wiki": sum(r["cites_wiki"] for r in rows),
        "mean_total_seconds": round(sum(r["timings"]["total"] for r in rows) / len(rows), 2),
        "seconds": round(time.time() - started),
    }
    out_dir = ROOT / "eval" / "runs"
    with (out_dir / f"{label}.jsonl").open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    (out_dir / f"{label}.scores.json").write_text(json.dumps(scores, indent=2))
    print(json.dumps(scores, indent=2))
    print("\nmisses:")
    for r in rows:
        if not r["correct"]:
            print(f"  {r['question']!r} (scope {r['scope']}; wanted {r['must_contain']})\n"
                  f"    -> {r['answer'][:220]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
