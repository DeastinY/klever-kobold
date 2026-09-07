#!/usr/bin/env python3
"""Fine-tune the retriever on the corpus's own description-to-entry pairs.

Descriptive questions are where retrieval still fails: "a way to patch up an ally
mid-fight", "the item you need to pick locks". The pipeline handles them by having
the model write the one-line summary the answering entry would have, then matching
that against a summary index. So the retriever's job on those queries is to match
a *description* to an *entry* -- and the corpus already contains 40,000 examples
of exactly that pairing, because every entry ships with its own one-line summary.

No teacher model, no generated data, no cost beyond the training run. The one
published PF2e embedder turned out to be numerically identical to its base, so
this is the first in-domain retriever this domain has actually had.

**The first attempt at this failed instructively.** Using the entry text unchanged
as the positive made recall *worse* by twelve points, because an entry's summary
appears verbatim inside its own text: the anchor was a substring of the target, so
matching them required no paraphrase, and the gradient went entirely into pushing
in-batch negatives apart. Mean pairwise cosine across the corpus fell from 0.344
to 0.045 -- uniformity without alignment.

So the positive now has the summary sentence removed (``--strip-anchor``). The
anchor describes what the entry does; the positive is the same thing said in
rulebook language, with no shared surface form to shortcut through. That is the
alignment signal the first run never had.

Trained with in-batch negatives: every other entry in the batch is a negative for
this summary, which is the right shape for a retrieval objective.

**Hygiene:** entries cited by any benchmark are excluded, so the retriever is never
shown a description of something it will be asked to find.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import random
import sys

import orjson

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pf2etune import retrieval  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="Qwen/Qwen3-Embedding-0.6B")
    ap.add_argument("--chunks", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "aon_chunks.jsonl")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "outputs" / "embed-pf2e")
    ap.add_argument("--epochs", type=float, default=1.0)
    ap.add_argument("--batch-size", type=int, default=48)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--max-chars", type=int, default=1200)
    ap.add_argument("--eval-frac", type=float, default=0.03)
    ap.add_argument("--seed", type=int, default=23)
    ap.add_argument("--strip-anchor", action="store_true", default=True,
                    help="remove the summary from the positive so the anchor is not a substring")
    ap.add_argument("--no-strip-anchor", dest="strip_anchor", action="store_false")
    args = ap.parse_args()

    import torch
    from datasets import Dataset
    from sentence_transformers import SentenceTransformer, SentenceTransformerTrainer
    from sentence_transformers import SentenceTransformerTrainingArguments
    from sentence_transformers.losses import CachedMultipleNegativesRankingLoss

    rows = [orjson.loads(l) for l in args.chunks.open("rb")]

    banned: set[str] = set()
    for name in ("benchmark.jsonl", "holdout.jsonl", "wild.jsonl", "wild_clean.jsonl"):
        path = ROOT / "eval" / name
        if not path.exists():
            continue
        for line in path.open("rb"):
            item = orjson.loads(line)
            banned.update(item.get("source_ids") or [])
            banned.update(item.get("alt_source_ids") or [])
    print(f"excluding {len(banned)} benchmark-cited entries")

    pairs = []
    for r in rows:
        if r["id"] in banned or not r.get("summary") or not r.get("name"):
            continue
        summary = r["summary"].strip()
        if len(summary) < 25:
            continue
        positive = retrieval.chunk_text(r, args.max_chars)
        if args.strip_anchor:
            # Remove the anchor's own words from the target. Without this the task
            # is substring matching and teaches nothing about paraphrase.
            positive = positive.replace(summary, " ")
            if summary[:60] in positive:
                positive = positive.replace(summary[:60], " ")
            positive = " ".join(positive.split())
            if len(positive) < 200:
                continue
        pairs.append({"anchor": summary, "positive": positive})
    random.Random(args.seed).shuffle(pairs)
    print(f"{len(pairs):,} description/entry pairs")

    dataset = Dataset.from_list(pairs)
    split = dataset.train_test_split(test_size=args.eval_frac, seed=args.seed)
    print(f"{len(split['train']):,} train / {len(split['test']):,} held out")

    model = SentenceTransformer(args.base, device="cuda")
    model.max_seq_length = 512
    # Cached MNRL keeps a large effective batch of in-batch negatives without
    # holding every activation: a retrieval objective wants many negatives, and
    # 41k entries on one card cannot afford them the naive way.
    loss = CachedMultipleNegativesRankingLoss(model, mini_batch_size=8)

    config = SentenceTransformerTrainingArguments(
        output_dir=str(args.out),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        learning_rate=args.lr,
        warmup_ratio=0.05,
        bf16=True,
        logging_steps=25,
        eval_strategy="steps",
        eval_steps=200,
        save_strategy="steps",
        save_steps=400,
        save_total_limit=2,
        report_to=[],
        seed=args.seed,
    )
    trainer = SentenceTransformerTrainer(
        model=model, args=config, train_dataset=split["train"],
        eval_dataset=split["test"], loss=loss,
    )
    trainer.train()
    model.save_pretrained(str(args.out / "final"))
    print(f"saved -> {args.out / 'final'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
