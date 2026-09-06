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

# The retrieval prompt has to differ -- the model needs telling that excerpts are
# authoritative and that their absence is an answer. It still says nothing about
# D&D 5e, so the contamination measurement stays uncontaminated by the prompt.
SYSTEM_RAG = (
    "You are answering questions about the Pathfinder Second Edition tabletop roleplaying game. "
    "Rules excerpts from the Archives of Nethys are provided below. Treat them as authoritative "
    "and prefer them over your own recollection. Answer concisely and directly, and cite the "
    "source URL of any excerpt you use. If the excerpts do not contain the answer, say so plainly "
    "rather than guessing."
)


def format_context(hits: list[tuple[str, dict]], bodies: dict[str, str], max_chars: int) -> str:
    blocks = []
    for n, (chunk_id, meta) in enumerate(hits, 1):
        head = f"[{n}] {meta.get('name')} ({meta.get('category', '').replace('-', ' ')}"
        if meta.get("level") is not None:
            head += f", level {meta['level']}"
        head += f") — {meta.get('url')}"
        blocks.append(head + "\n" + (bodies.get(chunk_id, "") or "")[:max_chars].strip())
    return "<rules_excerpts>\n" + "\n\n".join(blocks) + "\n</rules_excerpts>"


# --- OpenAI-compatible backend ---------------------------------------------

def _chat(client: httpx.Client, url: str, headers: dict, model: str, question: str,
          max_tokens: int, reasoning_effort: str | None, system: str = SYSTEM) -> tuple[str, dict]:
    body: dict = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": question}],
        "max_completion_tokens": max_tokens,
    }
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort

    last = ""
    for attempt in range(8):
        try:
            r = client.post(url, headers=headers, json=body, timeout=300.0)
        except httpx.HTTPError as exc:  # transport hiccup, not a refusal
            last = f"{type(exc).__name__}: {exc}"
            time.sleep(min(2**attempt, 60))
            continue
        if r.status_code == 400 and "max_completion_tokens" in r.text:
            body["max_tokens"] = body.pop("max_completion_tokens")  # older / non-OpenAI servers
            continue
        if r.status_code in (408, 409, 429, 500, 502, 503, 504, 529):
            last = f"HTTP {r.status_code}: {r.text[:200]}"
            # Rate limits on a long-context run need real backoff, not 16 seconds.
            time.sleep(min(2**attempt, 60))
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code} on {question[:50]!r}: {r.text[:300]}")
        data = orjson.loads(r.content)
        return data["choices"][0]["message"].get("content") or "", data.get("usage", {})
    raise RuntimeError(f"giving up after 8 attempts on {question[:50]!r}; last: {last}")


def run_api(items: list[dict], model: str, base_url: str, api_key: str, workers: int,
            max_tokens: int, reasoning_effort: str | None, system: str = SYSTEM) -> list[dict]:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    out: list[dict] = []
    done = 0

    with httpx.Client() as client:
        def one(item: dict) -> dict:
            text, usage = _chat(client, url, headers, model, item["prompt"], max_tokens,
                                reasoning_effort, system)
            return {"id": item["id"], "family": item["family"], "response": text,
                    "usage": usage, "retrieved": item.get("retrieved")}

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
           load_4bit: bool, chat_kwargs: dict, system: str = SYSTEM,
           adapter: pathlib.Path | None = None) -> list[dict]:
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
    if adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, str(adapter))
        print(f"  applied adapter {adapter}")
    model.eval()
    device = next(model.parameters()).device

    out: list[dict] = []
    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        prompts = [
            tok.apply_chat_template(
                [{"role": "system", "content": system}, {"role": "user", "content": it["prompt"]}],
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
                        "response": strip_thinking(text), "usage": {},
                        "retrieved": it.get("retrieved")})
        print(f"  {min(start + batch_size, len(items))}/{len(items)}", flush=True)
    return out


def attach_context(items: list[dict], retriever: str, mode: str, k: int,
                   context_chars: int, rewriter: str | None = None) -> None:
    """Retrieve for every item and fold the excerpts into its prompt.

    Mirrors eval/retrieval_eval.py exactly, including the query-time category
    narrowing, so the answers are graded on the same retrieval the recall numbers
    describe.
    """
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / "eval"))
    from pf2etune import retrieval as R
    import retrieval_eval

    index = retrieval_eval.load_index(retriever)
    bodies = {}
    for line in (ROOT / "data" / "processed" / "aon_chunks.jsonl").open("rb"):
        row = orjson.loads(line)
        bodies[row["id"]] = row["text"]

    parts = mode.split("+")
    base, hop = parts[0], "hop" in parts
    use_hyde, use_cat = "hyde" in parts, "cat" in parts

    rewrites = retrieval_eval.load_rewrites(rewriter) if (use_hyde or use_cat) else {}
    if (use_hyde or use_cat) and not rewrites:
        raise SystemExit(f"no cached rewrites for {rewriter}; run scripts/rewrite_queries.py")

    qvecs = retrieval_eval.encode_queries(retriever, [i["question"] for i in items])
    hyde_vecs = None
    if use_hyde:
        hyde_vecs = retrieval_eval.encode_queries(
            retriever, [(rewrites.get(i["question"]) or {}).get("summary") or i["question"]
                        for i in items])

    base_mask = index.allowed(exclude_legacy=not hop)
    pool = k * 2 if hop else k

    for n, (item, qvec) in enumerate(zip(items, qvecs)):
        mask = base_mask
        if use_cat:
            cats = (rewrites.get(item["question"]) or {}).get("categories") or []
            if cats:
                narrowed = base_mask & index.allowed(exclude_legacy=not hop, categories=cats)
                if narrowed.sum() >= k:
                    mask = narrowed
        if base == "bm25":
            order = index.lexical(item["question"], mask, pool)
        elif base == "dense":
            order = index.dense(qvec, mask, pool)
        elif base == "hybrid3":
            rankings = [index.dense(qvec, mask, 50),
                        index.dense(qvec, mask, 50, view="summary"),
                        index.lexical(item["question"], mask, 50)]
            if use_hyde and hyde_vecs is not None:
                rankings.append(index.dense(hyde_vecs[n], mask, 50, view="summary"))
                rankings.append(index.dense(hyde_vecs[n], mask, 50))
            order = R.rrf(rankings, pool)
        else:
            order = R.rrf([index.dense(qvec, mask, 50),
                           index.lexical(item["question"], mask, 50)], pool)
        if hop:
            order = R.follow_remaster(index, order)
        order = order[:k]
        hits = [(index.ids[i], index.meta[i]) for i in order]
        item["retrieved"] = [h[0] for h in hits]
        item["prompt"] = (format_context(hits, bodies, context_chars)
                          + "\n\nQuestion: " + item["question"])
    print(f"attached {k} excerpts per item via {retriever} / {mode}"
          + (f" / rewriter {rewriter}" if rewrites else ""))


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
    ap.add_argument("--adapter", type=pathlib.Path,
                    help="hf backend: LoRA adapter directory to load onto the base model")
    ap.add_argument("--chat-kwargs", default="{}",
                    help='hf backend: JSON passed to apply_chat_template, e.g. '
                         "'{\"enable_thinking\": false}'. Qwen3.x defaults to thinking at "
                         "xhigh effort, which is not what a plain baseline should measure.")
    ap.add_argument("--retry-empty", action="store_true",
                    help="re-run only the items whose response is empty in --out, and merge")
    ap.add_argument("--merge", action="store_true",
                    help="keep rows already in --out that this run does not cover")
    ap.add_argument("--retrieve", type=int, default=0, metavar="K",
                    help="prepend the top K retrieved rules excerpts to each question")
    ap.add_argument("--retriever", default="Qwen/Qwen3-Embedding-0.6B")
    ap.add_argument("--retrieval-mode", default="hybrid3+hyde+cat+hop")
    ap.add_argument("--rewriter", default="Qwen/Qwen3.5-9B",
                    help="model whose cached query rewrites to use")
    ap.add_argument("--context-chars", type=int, default=1600,
                    help="per-excerpt truncation")
    args = ap.parse_args()

    items = [orjson.loads(l) for l in args.benchmark.open("rb")]
    if args.family:
        items = [i for i in items if i["family"] in set(args.family)]
    if args.limit:
        items = items[:args.limit]

    system = SYSTEM_RAG if args.retrieve else SYSTEM
    if args.retrieve:
        attach_context(items, args.retriever, args.retrieval_mode, args.retrieve,
                       args.context_chars, args.rewriter)
    else:
        for it in items:
            it["prompt"] = it["question"]

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
                       args.max_tokens, args.reasoning_effort, system)
    else:
        rows = run_hf(items, args.model, args.max_tokens, args.batch_size, not args.no_4bit,
                      json.loads(args.chat_kwargs), system, args.adapter)

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
            "retrieval": ({"k": args.retrieve, "retriever": args.retriever,
                           "mode": args.retrieval_mode, "rewriter": args.rewriter,
                           "context_chars": args.context_chars}
                          if args.retrieve else None),
            "quantization": (None if args.backend == "api" else ("bf16" if args.no_4bit else "nf4-4bit")),
            "adapter": str(args.adapter) if args.adapter else None,
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
