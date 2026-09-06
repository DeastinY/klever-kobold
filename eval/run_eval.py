#!/usr/bin/env python3
"""Run the PF2e benchmark against a model and write responses for eval/score.py.

Two backends, one prompt:

``api``
    Any OpenAI-compatible ``/chat/completions`` endpoint -- api.openai.com for
    the frontier ceiling check, or a local vLLM / llama.cpp server via
    ``--base-url``.
``hf``
    ``transformers`` directly, 4-bit by default, for a local checkpoint with no
    server in front of it.

The prompt is deliberately neutral.  It names the game (otherwise the questions
are ambiguous) and permits abstention (otherwise the abstention family is a
trick), but it does not warn the model away from D&D 5e -- that would be
prompting away the very thing being measured.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import pathlib
import re
import sys
import time

import httpx
import orjson

ROOT = pathlib.Path(__file__).resolve().parents[1]

SYSTEM = (
    "You are answering questions about the Pathfinder Second Edition tabletop roleplaying game. "
    "Answer concisely and directly. If you do not know the answer, or the thing being asked about "
    "does not exist, say so plainly rather than guessing."
)


# --- OpenAI-compatible backend ---------------------------------------------

def _chat(client: httpx.Client, url: str, headers: dict, model: str, question: str,
          max_tokens: int, reasoning_effort: str | None) -> tuple[str, dict]:
    body: dict = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}],
        "max_completion_tokens": max_tokens,
    }
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort

    for attempt in range(5):
        r = client.post(url, headers=headers, json=body, timeout=180.0)
        if r.status_code == 400 and "max_completion_tokens" in r.text:
            body["max_tokens"] = body.pop("max_completion_tokens")  # older / non-OpenAI servers
            continue
        if r.status_code in (429, 500, 502, 503, 529):
            time.sleep(2**attempt)
            continue
        r.raise_for_status()
        data = orjson.loads(r.content)
        return data["choices"][0]["message"].get("content") or "", data.get("usage", {})
    raise RuntimeError(f"giving up on: {question[:60]}")


def run_api(items: list[dict], model: str, base_url: str, api_key: str, workers: int,
            max_tokens: int, reasoning_effort: str | None) -> list[dict]:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    out: list[dict] = []
    done = 0

    with httpx.Client() as client:
        def one(item: dict) -> dict:
            text, usage = _chat(client, url, headers, model, item["question"], max_tokens, reasoning_effort)
            return {"id": item["id"], "family": item["family"], "response": text, "usage": usage}

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for res in pool.map(one, items):
                out.append(res)
                done += 1
                if done % 25 == 0:
                    print(f"  {done}/{len(items)}", flush=True)
    return out


# --- local transformers backend --------------------------------------------

def _load_hf(model_id: str, quant):
    """Load a checkpoint whatever head class it declares.

    Qwen3.8-27B ships as ``Qwen3_5ForConditionalGeneration`` -- a multimodal
    checkpoint with a vision tower bolted to a text decoder -- so
    ``AutoModelForCausalLM`` does not map it. Try the image-text head first and
    fall back, rather than assuming a plain causal LM.
    """
    import torch
    from transformers import AutoConfig, AutoModel

    errors = []
    try:
        from transformers import AutoModelForImageTextToText
        candidates = [AutoModelForImageTextToText]
    except ImportError:  # pragma: no cover - older transformers
        candidates = []
    from transformers import AutoModelForCausalLM
    candidates += [AutoModelForCausalLM, AutoModel]

    for cls in candidates:
        try:
            model = cls.from_pretrained(
                model_id, quantization_config=quant, dtype=torch.bfloat16, device_map="auto",
            )
            print(f"  loaded via {cls.__name__} as {type(model).__name__}")
            return model
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(f"{cls.__name__}: {exc}")
    raise RuntimeError("could not load model:\n  " + "\n  ".join(errors))


RE_THINK = re.compile(r"^.*?</think>\s*", re.S)


def strip_thinking(text: str) -> str:
    """Drop a reasoning block so scoring sees the answer, not the deliberation."""
    if "</think>" in text:
        return RE_THINK.sub("", text, count=1).strip()
    return text.strip()


def run_hf(items: list[dict], model_id: str, max_tokens: int, batch_size: int,
           load_4bit: bool, chat_kwargs: dict) -> list[dict]:
    import torch
    from transformers import AutoTokenizer, BitsAndBytesConfig

    quant = None
    if load_4bit:
        quant = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )

    tok = AutoTokenizer.from_pretrained(model_id, padding_side="left")
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = _load_hf(model_id, quant)
    model.eval()
    device = next(model.parameters()).device

    out: list[dict] = []
    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        prompts = [
            tok.apply_chat_template(
                [{"role": "system", "content": SYSTEM}, {"role": "user", "content": it["question"]}],
                tokenize=False, add_generation_prompt=True, **chat_kwargs,
            )
            for it in batch
        ]
        enc = tok(prompts, return_tensors="pt", padding=True).to(device)
        with torch.inference_mode():
            # Greedy: the benchmark has to be reproducible, and the checkpoint's
            # generation_config defaults to sampling.
            gen = model.generate(**enc, max_new_tokens=max_tokens, do_sample=False,
                                 temperature=None, top_p=None, top_k=None,
                                 pad_token_id=tok.pad_token_id)
        for it, seq in zip(batch, gen):
            text = tok.decode(seq[enc["input_ids"].shape[1]:], skip_special_tokens=True)
            out.append({"id": it["id"], "family": it["family"],
                        "response": strip_thinking(text), "usage": {}})
        print(f"  {min(start + batch_size, len(items))}/{len(items)}", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--backend", choices=("api", "hf"), default="api")
    ap.add_argument("--benchmark", type=pathlib.Path, default=ROOT / "eval" / "benchmark.jsonl")
    ap.add_argument("--out", type=pathlib.Path, help="default: eval/runs/<label>.jsonl")
    ap.add_argument("--label", help="run name; defaults to a slug of the model id")
    ap.add_argument("--limit", type=int, help="first N items only, for smoke tests")
    ap.add_argument("--family", nargs="*", help="restrict to these families")
    ap.add_argument("--base-url", default="https://api.openai.com/v1")
    ap.add_argument("--api-key-env", default="OPENAI_API_KEY")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-tokens", type=int, default=1200)
    ap.add_argument("--reasoning-effort", help="e.g. low; omit for non-reasoning models")
    ap.add_argument("--batch-size", type=int, default=8, help="hf backend only")
    ap.add_argument("--no-4bit", action="store_true", help="hf backend: load in bf16 instead")
    ap.add_argument("--chat-kwargs", default="{}",
                    help='hf backend: JSON passed to apply_chat_template, e.g. '
                         "'{\"enable_thinking\": false}'. Qwen3.x defaults to thinking at "
                         "xhigh effort, which is not what a plain baseline should measure.")
    ap.add_argument("--retry-empty", action="store_true",
                    help="re-run only the items whose response is empty in --out, and merge")
    ap.add_argument("--merge", action="store_true",
                    help="keep rows already in --out that this run does not cover")
    args = ap.parse_args()

    items = [orjson.loads(l) for l in args.benchmark.open("rb")]
    if args.family:
        items = [i for i in items if i["family"] in set(args.family)]
    if args.limit:
        items = items[:args.limit]

    label = args.label or args.model.replace("/", "_").replace(":", "-")
    out_path = args.out or ROOT / "eval" / "runs" / f"{label}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    kept: list[dict] = []
    if args.merge and not args.retry_empty and out_path.exists():
        covered = {i["id"] for i in items}
        kept = [r for r in (orjson.loads(l) for l in out_path.open("rb")) if r["id"] not in covered]
        print(f"merging {len(items)} new into {len(kept)} existing")
    if args.retry_empty:
        if not out_path.exists():
            print(f"--retry-empty needs an existing {out_path}", file=sys.stderr)
            return 1
        previous = [orjson.loads(l) for l in out_path.open("rb")]
        kept = [r for r in previous if r["response"].strip()]
        redo = {r["id"] for r in previous if not r["response"].strip()}
        items = [i for i in items if i["id"] in redo]
        print(f"retrying {len(items)} empty of {len(previous)}")
        if not items:
            return 0

    print(f"{label}: {len(items)} items via {args.backend}")
    started = time.time()

    if args.backend == "api":
        key = os.environ.get(args.api_key_env, "")
        if not key and "localhost" not in args.base_url and "127.0.0.1" not in args.base_url:
            print(f"${args.api_key_env} is not set", file=sys.stderr)
            return 1
        rows = run_api(items, args.model, args.base_url, key, args.workers,
                       args.max_tokens, args.reasoning_effort)
    else:
        rows = run_hf(items, args.model, args.max_tokens, args.batch_size, not args.no_4bit,
                      json.loads(args.chat_kwargs))

    rows = kept + rows
    rows.sort(key=lambda r: r["id"])
    with out_path.open("wb") as fh:
        for row in rows:
            fh.write(orjson.dumps(row))
            fh.write(b"\n")

    usage = {
        "prompt_tokens": sum(r["usage"].get("prompt_tokens", 0) for r in rows),
        "completion_tokens": sum(r["usage"].get("completion_tokens", 0) for r in rows),
    }
    meta = {"label": label, "model": args.model, "backend": args.backend,
            "base_url": args.base_url if args.backend == "api" else None,
            "items": len(rows), "seconds": round(time.time() - started, 1),
            "max_tokens": args.max_tokens, "reasoning_effort": args.reasoning_effort,
            "chat_kwargs": json.loads(args.chat_kwargs) if args.backend == "hf" else None,
            "quantization": (None if args.backend == "api" else ("bf16" if args.no_4bit else "nf4-4bit")),
            "usage": usage, "empty_responses": sum(1 for r in rows if not r["response"].strip())}
    out_path.with_suffix(".meta.json").write_bytes(orjson.dumps(meta, option=orjson.OPT_INDENT_2))

    print(f"wrote {out_path}  ({meta['seconds']}s"
          + (f", {usage['prompt_tokens']:,} in / {usage['completion_tokens']:,} out" if usage["completion_tokens"] else "")
          + ")")
    if meta["empty_responses"]:
        print(f"warning: {meta['empty_responses']} empty responses", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
