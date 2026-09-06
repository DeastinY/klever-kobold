#!/usr/bin/env python3
"""Can the model pick the right excerpt, when picking is all it has to do?

Free-text answering conflates two abilities: choosing which retrieved excerpt is
relevant, and writing a correct answer from it. This probe isolates the first.
The model is shown the same five excerpts and asked for a single character --
1-5, or N for "none of these" -- and we read the logits for exactly those six
tokens. Nothing is generated, so nothing can be hallucinated, and one forward
pass per item makes the whole benchmark a two-minute experiment.

That constraint is also a candidate fix rather than only a diagnostic. Abstention
is the project's one unsolved family, and as free text it is a behaviour the
model has to volunteer. As a choice among six options it is a classification with
a correct answer -- 'N' -- that the model is forced to consider every time.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import sys

import orjson

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

CHOICES = ["1", "2", "3", "4", "5", "N"]

INSTRUCTION = (
    "Below are numbered rules excerpts from the Archives of Nethys, then a question.\n"
    "Reply with a single character and nothing else: the number of the one excerpt that "
    "answers the question, or N if none of them does.\n"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen3.5-9B")
    ap.add_argument("--adapter", type=pathlib.Path)
    ap.add_argument("--benchmark", type=pathlib.Path, default=ROOT / "eval" / "benchmark.jsonl")
    ap.add_argument("--retriever", default="Kaylebor/pf2e-codex-embed-xs")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--context-chars", type=int, default=1600)
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "eval" / "runs" / "selection.scores.json")
    args = ap.parse_args()

    import torch
    from transformers import AutoTokenizer, BitsAndBytesConfig
    from run_eval import _load_hf, attach_context

    items = [orjson.loads(l) for l in args.benchmark.open("rb")
             if not orjson.loads(l).get("excluded")]
    # Only families with a gold chunk, plus abstention, have a defined right answer.
    items = [i for i in items if i["source_ids"] or i["family"] == "abstention"]
    attach_context(items, args.retriever, "hybrid+hop", args.k, args.context_chars)

    tok = AutoTokenizer.from_pretrained(args.model, padding_side="left")
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                              bnb_4bit_compute_dtype=torch.bfloat16,
                              bnb_4bit_use_double_quant=True)
    model = _load_hf(args.model, quant)
    if args.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, str(args.adapter))
        print(f"  applied adapter {args.adapter}")
    model.eval()
    device = next(model.parameters()).device

    choice_ids = [tok.encode(c, add_special_tokens=False)[0] for c in CHOICES]
    assert len(set(choice_ids)) == len(CHOICES), "choice tokens collide"

    results = []
    for start in range(0, len(items), args.batch_size):
        batch = items[start:start + args.batch_size]
        prompts = [
            tok.apply_chat_template(
                [{"role": "user", "content": INSTRUCTION + "\n" + it["prompt"]}],
                tokenize=False, add_generation_prompt=True, enable_thinking=False)
            for it in batch
        ]
        enc = tok(prompts, return_tensors="pt", padding=True).to(device)
        with torch.inference_mode():
            logits = model(**enc).logits[:, -1, :]
        picked = logits[:, choice_ids].argmax(dim=-1).tolist()
        for it, p in zip(batch, picked):
            gold_ids = set(it["source_ids"]) | set(it.get("alt_source_ids") or [])
            retrieved = it["retrieved"]
            correct_slots = {str(n + 1) for n, cid in enumerate(retrieved) if cid in gold_ids}
            expected = correct_slots or {"N"}
            results.append({"id": it["id"], "family": it["family"],
                            "choice": CHOICES[p], "expected": sorted(expected),
                            "correct": CHOICES[p] in expected})
        if (start // args.batch_size) % 20 == 0:
            print(f"  {min(start + args.batch_size, len(items))}/{len(items)}", flush=True)

    by_family: dict[str, dict] = collections.defaultdict(lambda: {"n": 0, "correct": 0})
    for r in results:
        f = by_family[r["family"]]
        f["n"] += 1
        f["correct"] += r["correct"]

    label = f"{args.model}{' + ' + args.adapter.name if args.adapter else ''}"
    print(f"\nselection accuracy — {label}\n")
    print(f"  {'family':18s} {'n':>4s} {'correct':>8s} {'acc':>7s}")
    for fam, v in sorted(by_family.items()):
        print(f"  {fam:18s} {v['n']:4d} {v['correct']:8d} {v['correct'] / v['n']:6.1%}")
    total = len(results)
    hit = sum(r["correct"] for r in results)
    print(f"\n  {'overall':18s} {total:4d} {hit:8d} {hit / total:6.1%}")

    chose_n = sum(1 for r in results if r["choice"] == "N")
    should_n = sum(1 for r in results if r["expected"] == ["N"])
    print(f"  chose N: {chose_n}   should have: {should_n}")

    args.out.write_bytes(orjson.dumps(
        {"model": args.model, "adapter": str(args.adapter) if args.adapter else None,
         "overall": hit / total, "families": dict(by_family),
         "chose_none": chose_n, "should_choose_none": should_n,
         "results": results}, option=orjson.OPT_INDENT_2))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
