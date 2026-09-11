#!/usr/bin/env python3
"""Expand player questions into things the retriever can actually match.

The retriever indexes game entities. Players ask about situations, and the two
share almost no vocabulary: "an ogre has grabbed my monk, what can she do?"
retrieves the Escape action 7.7% of the time.

The obvious fix -- ask the model to name the rules elements -- fails, and fails
predictably. Naming is the model's *worst* measured skill on this corpus (17% on
feat levels closed-book), and the first attempt duly answered "Path of the Totem
Warrior" and "Daring Attack", neither of which exists. Asking a model to recall
what it does not know produces fluent nonsense.

So this asks for two things it is actually good at:

``summary``
    A hypothetical one-line database summary of the entry that would answer the
    question. Pure paraphrase, no recall. It is embedded and matched against the
    *summary* index, whose entries are one-line descriptions -- so the generated
    text and the target text are drawn from the same distribution. (This is HyDE,
    narrowed to the shape of the field it searches.)
``categories``
    Which kinds of entry could answer this. A situational question needs actions
    and conditions, not the 9,000 pieces of equipment that dominate the corpus.

Both degrade safely: a wrong summary is one more ranking among four fused, and a
wrong category list is dropped unless it parses to known categories.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

import orjson

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))

CATEGORIES = ("action", "condition", "feat", "spell", "equipment", "weapon", "armor",
              "creature", "hazard", "trait", "rules", "class-feature", "ritual",
              "archetype", "background", "heritage", "deity", "shield")

SYSTEM = (
    "You help search a Pathfinder 2e rules database. Each entry is one game element with a "
    "one-line summary.\n\n"
    "Given a player's question, reply with exactly two lines and nothing else:\n"
    "SUMMARY: the one-line summary you would expect on the database entry that answers this "
    "question, written the way the rulebook writes summaries. Describe what it does. Do not "
    "guess at a name.\n"
    "KINDS: up to three entry kinds that could answer it, comma separated, from: "
    + ", ".join(CATEGORIES) + "\n\n"
    "Question: An ogre has grabbed my monk. What can she do about it on her turn?\n"
    "SUMMARY: Attempt to escape from being grabbed, immobilized, or restrained.\n"
    "KINDS: action, condition\n\n"
    "Question: Is there a feat that makes falling less dangerous?\n"
    "SUMMARY: Treat falls as shorter than they are.\n"
    "KINDS: feat\n\n"
    "Question: How much healing does a short rest give my party?\n"
    "SUMMARY: Spend 10 minutes treating an injured creature to restore Hit Points.\n"
    "KINDS: action, feat"
)

RE_CLEAN = re.compile(r"^[\s\-*\d.)]+|[\s;:]+$")


def parse(text: str) -> dict:
    summary, kinds = "", []
    for line in (text or "").splitlines():
        line = line.strip()
        if line.upper().startswith("SUMMARY:"):
            summary = RE_CLEAN.sub("", line.split(":", 1)[1]).strip()
        elif line.upper().startswith("KINDS:"):
            for part in line.split(":", 1)[1].split(","):
                part = part.strip().lower().replace(" ", "-")
                if part in CATEGORIES and part not in kinds:
                    kinds.append(part)
    return {"summary": summary[:220], "categories": kinds[:3]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen3.8-27B")
    ap.add_argument("--benchmark", type=pathlib.Path, default=ROOT / "eval" / "holdout.jsonl")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "query_rewrites.json")
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--max-tokens", type=int, default=90)
    args = ap.parse_args()

    import torch
    from run_eval import _load_hf
    from transformers import AutoTokenizer, BitsAndBytesConfig

    questions = [orjson.loads(line)["question"] for line in args.benchmark.open("rb")]
    cache = orjson.loads(args.out.read_bytes()) if args.out.exists() else {}
    def key(q):
        return f"{args.model}|{q}"
    todo = [q for q in questions if key(q) not in cache]
    print(f"{len(questions)} questions, {len(todo)} to rewrite")
    if not todo:
        return 0

    tok = AutoTokenizer.from_pretrained(args.model, padding_side="left")
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                              bnb_4bit_compute_dtype=torch.bfloat16,
                              bnb_4bit_use_double_quant=True)
    model = _load_hf(args.model, quant)
    model.eval()
    device = next(model.parameters()).device

    for start in range(0, len(todo), args.batch_size):
        batch = todo[start:start + args.batch_size]
        prompts = [
            tok.apply_chat_template(
                [{"role": "system", "content": SYSTEM},
                 {"role": "user", "content": f"Question: {q}"}],
                tokenize=False, add_generation_prompt=True, enable_thinking=False)
            for q in batch
        ]
        enc = tok(prompts, return_tensors="pt", padding=True).to(device)
        with torch.inference_mode():
            gen = model.generate(**enc, max_new_tokens=args.max_tokens, do_sample=False,
                                 temperature=None, top_p=None, top_k=None,
                                 pad_token_id=tok.pad_token_id)
        for q, seq in zip(batch, gen, strict=False):
            text = tok.decode(seq[enc["input_ids"].shape[1]:], skip_special_tokens=True)
            cache[key(q)] = parse(text)
        print(f"  {min(start + args.batch_size, len(todo))}/{len(todo)}", flush=True)

    args.out.write_bytes(orjson.dumps(cache, option=orjson.OPT_INDENT_2))
    empty = sum(1 for q in questions if not (cache.get(key(q)) or {}).get("summary"))
    print(f"\nwrote {args.out}  ({len(cache)} cached, {empty} produced no summary)")
    for q in questions[:4]:
        v = cache.get(key(q), {})
        print(f"  {q[:62]}\n     -> {v.get('summary','')[:78]}  {v.get('categories')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
