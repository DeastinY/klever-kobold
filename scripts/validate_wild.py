#!/usr/bin/env python3
"""Check whether a mined label actually answers its question.

The mined set takes its gold entries from the Archives of Nethys pages an accepted
answer links to. That is a good signal and not a perfect one: answers link
tangentially, cite a page for a definition they use in passing, or argue from a
rules chapter that is context rather than answer.

The recall curve says how bad it is. A generous retrieval over the whole corpus
finds 95.5% of hand-written golds within 300 results and only 64.0% of mined ones
-- so roughly a third of mined labels are not merely hard to rank, they are not
findable, which is what an unanswerable label looks like.

Filtering by whether *this* retriever can find them would be circular: it would
delete exactly the questions the set exists to expose. So the judge never sees a
ranking. It sees the question and the text of the cited entry and answers one
question: does this entry contain what is needed? That is a statement about the
label, not about the retriever.
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
    "You are checking whether a rules database entry answers a Pathfinder 2e question.\n"
    "You will see the question and the full text of one entry.\n"
    "Reply with exactly one word:\n"
    "ANSWERS   — the entry contains what is needed to answer the question, or a substantial part "
    "of it.\n"
    "CONTEXT   — the entry is related and useful background, but the answer is not in it.\n"
    "UNRELATED — the entry has little to do with the question.\n"
    "One word. Nothing else."
)

RE_VERDICT = re.compile(r"\b(ANSWERS|CONTEXT|UNRELATED)\b", re.I)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wild", type=pathlib.Path, default=ROOT / "eval" / "wild.jsonl")
    ap.add_argument("--chunks", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "aon_chunks.jsonl")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "eval" / "wild_clean.jsonl")
    ap.add_argument("--verdicts", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "wild_verdicts.json")
    ap.add_argument("--judge", default="Qwen/Qwen3.8-27B")
    ap.add_argument("--batch-size", type=int, default=3)
    ap.add_argument("--entry-chars", type=int, default=1800)
    args = ap.parse_args()

    import torch
    from transformers import AutoTokenizer, BitsAndBytesConfig
    from run_eval import _load_hf, strip_thinking

    bodies = {}
    for line in args.chunks.open("rb"):
        r = orjson.loads(line)
        bodies[r["id"]] = (r["name"], r["category"], r["text"] or "")
    items = [orjson.loads(l) for l in args.wild.open("rb")]

    cache = orjson.loads(args.verdicts.read_bytes()) if args.verdicts.exists() else {}
    todo = [(it, sid) for it in items for sid in it["source_ids"]
            if f"{it['id']}|{sid}" not in cache and sid in bodies]
    print(f"{len(items)} items, {len(todo)} (item, entry) pairs to judge")

    if todo:
        tok = AutoTokenizer.from_pretrained(args.judge, padding_side="left")
        if tok.pad_token is None:
            tok.pad_token = tok.eos_token
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                  bnb_4bit_compute_dtype=torch.bfloat16,
                                  bnb_4bit_use_double_quant=True)
        model = _load_hf(args.judge, quant)
        model.eval()
        device = next(model.parameters()).device

        for start in range(0, len(todo), args.batch_size):
            batch = todo[start:start + args.batch_size]
            prompts = []
            for it, sid in batch:
                name, category, text = bodies[sid]
                question = it["question"]
                if it.get("detail"):
                    question += "\n" + it["detail"][:300]
                prompts.append(tok.apply_chat_template(
                    [{"role": "system", "content": JUDGE},
                     {"role": "user", "content":
                      f"Question: {question}\n\nEntry: {name} ({category})\n"
                      f"{text[:args.entry_chars]}"}],
                    tokenize=False, add_generation_prompt=True, enable_thinking=False))
            enc = tok(prompts, return_tensors="pt", padding=True).to(device)
            with torch.inference_mode():
                gen = model.generate(**enc, max_new_tokens=8, do_sample=False,
                                     temperature=None, top_p=None, top_k=None,
                                     pad_token_id=tok.pad_token_id)
            for (it, sid), seq in zip(batch, gen):
                text = strip_thinking(tok.decode(seq[enc["input_ids"].shape[1]:],
                                                 skip_special_tokens=True))
                m = RE_VERDICT.search(text)
                cache[f"{it['id']}|{sid}"] = m.group(1).upper() if m else "UNPARSED"
            if (start // args.batch_size) % 20 == 0:
                print(f"  {min(start + args.batch_size, len(todo))}/{len(todo)}", flush=True)
        args.verdicts.write_bytes(orjson.dumps(cache, option=orjson.OPT_INDENT_2))

    counts = collections.Counter(cache.values())
    kept = []
    for it in items:
        good = [sid for sid in it["source_ids"]
                if cache.get(f"{it['id']}|{sid}") == "ANSWERS"]
        if not good:
            continue
        item = dict(it)
        item["source_ids"] = good
        item["source_urls"] = [u for sid, u in zip(it["source_ids"], it["source_urls"])
                               if sid in good]
        item["family"] = "wild_answerable"
        kept.append(item)

    with args.out.open("wb") as fh:
        for item in kept:
            fh.write(orjson.dumps(item))
            fh.write(b"\n")

    print(f"\nverdicts: {dict(counts)}")
    print(f"kept {len(kept)} of {len(items)} questions with at least one answering entry "
          f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
