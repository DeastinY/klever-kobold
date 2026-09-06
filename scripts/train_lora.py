#!/usr/bin/env python3
"""QLoRA training on RAFT data.

Targets only the text decoder. Qwen3.5-9B carries a vision tower
(``model.visual.*``, 333 tensors) and a multi-token-prediction head
(``mtp.*``) alongside the language model; adapting either would spend rank on
parameters this task never exercises, so the target regex names
``model.language_model.layers.N`` explicitly rather than matching ``q_proj``
everywhere.

Loss is computed on the assistant turn only, via TRL's prompt/completion format.
Training on the prompt would spend most of the gradient on 5,000 tokens of
retrieved rules text -- teaching the model to *write* Archives of Nethys entries,
which is not the behaviour under test.

The chat template is rendered here rather than left to TRL, because Qwen3.x
templates default to ``enable_thinking=True`` and inject reasoning instructions
into the system turn. Evaluation runs with thinking off, and a model trained
under one system prompt and measured under another is measuring the mismatch.
"""

from __future__ import annotations

import argparse
import pathlib

import orjson

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Attention and MLP projections inside the language model, and nowhere else.
TARGETS = (
    r"model\.language_model\.layers\.\d+\."
    r"(?:self_attn\.(?:q|k|v|o)_proj|mlp\.(?:gate|up|down)_proj)"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen3.5-9B")
    ap.add_argument("--data", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "raft_train.jsonl")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "outputs" / "raft-9b")
    ap.add_argument("--rank", type=int, default=32)
    ap.add_argument("--alpha", type=int, default=64)
    ap.add_argument("--dropout", type=float, default=0.05)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--max-length", type=int, default=3072)
    ap.add_argument("--eval-frac", type=float, default=0.04)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--no-grad-checkpointing", action="store_true",
                    help="~30%% faster and fits at this sequence length on 32 GB")
    args = ap.parse_args()

    import torch
    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    import sys
    sys.path.insert(0, str(ROOT / "eval"))
    from run_eval import _load_hf

    tok = AutoTokenizer.from_pretrained(args.model)
    rows = [orjson.loads(l) for l in args.data.open("rb")]
    records = []
    for r in rows:
        msgs = r["messages"]
        prompt = tok.apply_chat_template(msgs[:-1], tokenize=False,
                                         add_generation_prompt=True, enable_thinking=False)
        full = tok.apply_chat_template(msgs, tokenize=False, enable_thinking=False)
        if not full.startswith(prompt):
            raise SystemExit("chat template is not prefix-stable; cannot split prompt/completion")
        records.append({"prompt": prompt, "completion": full[len(prompt):], "kind": r["kind"]})
    print(f"prompt/completion rendered with thinking disabled; "
          f"example completion: {records[0]['completion'][:80]!r}")
    dataset = Dataset.from_list(records).shuffle(seed=args.seed)
    split = dataset.train_test_split(test_size=args.eval_frac, seed=args.seed)
    print(f"{len(split['train']):,} train / {len(split['test']):,} held out")

    quant = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True,
    )
    model = _load_hf(args.model, quant)
    model.config.use_cache = False

    peft_config = LoraConfig(
        r=args.rank, lora_alpha=args.alpha, lora_dropout=args.dropout,
        bias="none", task_type="CAUSAL_LM", target_modules=TARGETS,
    )

    config = SFTConfig(
        output_dir=str(args.out),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_steps=20,
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=50,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=3,
        bf16=True,
        max_length=args.max_length,
        gradient_checkpointing=not args.no_grad_checkpointing,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="paged_adamw_8bit",
        report_to=[],
        seed=args.seed,
        completion_only_loss=True,
    )

    trainer = SFTTrainer(
        model=model, args=config, processing_class=tok,
        train_dataset=split["train"], eval_dataset=split["test"],
        peft_config=peft_config,
    )
    trainable = sum(p.numel() for p in trainer.model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in trainer.model.parameters())
    print(f"trainable {trainable / 1e6:.1f}M / {total / 1e9:.2f}B ({trainable / total:.2%})")

    trainer.train()
    trainer.save_model(str(args.out / "final"))
    print(f"saved adapter -> {args.out / 'final'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
