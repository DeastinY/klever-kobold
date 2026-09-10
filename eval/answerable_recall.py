#!/usr/bin/env python3
"""Does the retrieved set answer the question? -- rather than does it contain one chunk.

Exact-chunk recall has been the screen for every retrieval decision here, and two
increments in a row exposed it. Increment 6 showed it can move opposite to answer
quality. This one shows it is often simply wrong about what a miss is:

    "Can I have just a striking weapon?"  label: Runes        found: Fundamental Runes
    "Action cost of drawing a weapon?"    label: Wielding Items found: Drawing and Stowing Items
    "Will uneven speed round up or down?" label: General Rules  found: Speed, Round

Every one of those counts as a miss and every one retrieved a page at least as
good as the label. The Archives of Nethys rules chapters nest, humans cite
whichever level they happened to have open, and an exact-id match cannot tell a
genuine failure from a difference of granularity.

So this asks the question the system is actually judged on: shown the excerpts it
retrieved, can they be answered from? One judgement per question rather than one
per entry, the judge sees names, summaries and truncated text, and it never sees
which entry was the label.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import re
import sys

import orjson

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

JUDGE = (
    "You are checking whether a set of Pathfinder 2e rules excerpts is enough to answer a "
    "question.\n"
    "You will see a question and several numbered excerpts.\n"
    "Reply with exactly one word:\n"
    "YES  — the excerpts contain what is needed to answer, or the substance of it.\n"
    "PART — they cover the topic but the specific answer is not in them.\n"
    "NO   — they do not address the question.\n"
    "One word. Nothing else."
)
RE_VERDICT = re.compile(r"\b(YES|PART|NO)\b")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", type=pathlib.Path, default=ROOT / "eval" / "wild_clean.jsonl")
    ap.add_argument("--index", type=pathlib.Path, default=ROOT / "dist" / "kobold-index")
    ap.add_argument("--judge", default="Qwen/Qwen3.8-27B")
    ap.add_argument("-k", type=int, default=8)
    ap.add_argument("--excerpt-chars", type=int, default=520)
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--no-expand", action="store_true", help="disable one-hop link expansion")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "eval" / "runs" / "answerable_recall.json")
    args = ap.parse_args()

    import torch
    from transformers import AutoTokenizer, BitsAndBytesConfig
    from kleverkobold.app import Assistant
    from run_eval import _load_hf, strip_thinking

    a = Assistant(args.index)
    items = [orjson.loads(l) for l in args.benchmark.open("rb")]
    print(f"retrieving for {len(items)} questions")
    retrieved = [a.search(it["question"], k=args.k, rerank=not args.no_rerank,
                          expand=0 if args.no_expand else None or 3) for it in items]
    # Ollama keeps models resident server-side after the last call, so the 27B
    # judge cannot fit alongside them. keep_alive=0 unloads immediately.
    import httpx
    for model in (a.manifest["ollama_llm"], a.manifest["ollama_embed"]):
        try:
            httpx.post(f"{a.ollama.base_url}/api/generate",
                       json={"model": model, "keep_alive": 0}, timeout=30.0)
        except httpx.HTTPError:
            pass
    del a

    tok = AutoTokenizer.from_pretrained(args.judge, padding_side="left")
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                              bnb_4bit_compute_dtype=torch.bfloat16,
                              bnb_4bit_use_double_quant=True)
    model = _load_hf(args.judge, quant)
    model.eval()
    device = next(model.parameters()).device

    verdicts = []
    for start in range(0, len(items), args.batch_size):
        batch = list(zip(items, retrieved))[start:start + args.batch_size]
        prompts = []
        for it, hits in batch:
            excerpts = "\n\n".join(
                f"{n}. {h.name} ({h.category.replace('-', ' ')})\n"
                f"{(h.text or '')[:args.excerpt_chars].strip()}"
                for n, h in enumerate(hits, 1))
            question = it["question"]
            if it.get("detail"):
                question += "\n" + it["detail"][:300]
            prompts.append(tok.apply_chat_template(
                [{"role": "system", "content": JUDGE},
                 {"role": "user", "content": f"Question: {question}\n\n{excerpts}"}],
                tokenize=False, add_generation_prompt=True, enable_thinking=False))
        enc = tok(prompts, return_tensors="pt", padding=True).to(device)
        with torch.inference_mode():
            gen = model.generate(**enc, max_new_tokens=6, do_sample=False,
                                 temperature=None, top_p=None, top_k=None,
                                 pad_token_id=tok.pad_token_id)
        for (it, _), seq in zip(batch, gen):
            text = strip_thinking(tok.decode(seq[enc["input_ids"].shape[1]:],
                                             skip_special_tokens=True))
            m = RE_VERDICT.search(text.upper())
            verdicts.append({"id": it["id"], "verdict": m.group(1) if m else "UNPARSED"})
        if (start // args.batch_size) % 15 == 0:
            print(f"  {min(start + args.batch_size, len(items))}/{len(items)}", flush=True)

    counts = collections.Counter(v["verdict"] for v in verdicts)
    n = len(verdicts)
    print(f"\n{args.benchmark.name}  k={args.k}"
          f"{'  (no rerank)' if args.no_rerank else ''}")
    for verdict in ("YES", "PART", "NO", "UNPARSED"):
        if counts[verdict]:
            print(f"  {verdict:9s} {counts[verdict]:4d}  {counts[verdict] / n:6.1%}")
    print(f"\n  answerable from what was retrieved: {counts['YES'] / n:.1%}")
    args.out.write_bytes(orjson.dumps(
        {"benchmark": args.benchmark.name, "k": args.k, "rerank": not args.no_rerank,
         "counts": dict(counts), "verdicts": verdicts}, option=orjson.OPT_INDENT_2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
