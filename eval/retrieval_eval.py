#!/usr/bin/env python3
"""Score the retriever on its own, before any model sees a chunk.

The benchmark was generated *from* the corpus, so 400 of its 486 items carry the
id of the exact chunk their answer came from.  That gives gold retrieval labels
for free -- no annotation, no judge -- and lets the two halves of a RAG system be
diagnosed separately:

    did retrieval surface the right chunk?      <- measured here
    given the right chunk, was the answer right? <- measured by run_eval + score

The gap between those two is the size of the model's prior problem, and the whole
justification for fine-tuning rather than just indexing harder.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import pickle
import sys
import time

import numpy as np
import orjson

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pf2etune import retrieval  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "processed" / "index"
KS = (1, 5, 20)


def load_index(model_name: str | None, want_bm25: bool = True) -> retrieval.Index:
    meta = [orjson.loads(l) for l in (INDEX / "meta.jsonl").open("rb")]
    ids = [m["id"] for m in meta]
    emb = None
    if model_name:
        path = INDEX / f"emb__{model_name.replace('/', '__')}.npy"
        if not path.exists():
            raise SystemExit(f"missing {path}; run scripts/build_index.py --model {model_name}")
        emb = np.load(path)
    bm25 = pickle.loads((INDEX / "bm25.pkl").read_bytes()) if want_bm25 else None
    return retrieval.Index(ids=ids, meta=meta, embeddings=emb, bm25=bm25, model_name=model_name)


def encode_queries(model_name: str, queries: list[str]) -> np.ndarray:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name, device="cuda")
    kwargs = {}
    # Asymmetric retrievers want the query side marked. Honour whatever the
    # checkpoint declares rather than hard-coding a prefix per family.
    if getattr(model, "prompts", None) and "query" in model.prompts:
        kwargs["prompt_name"] = "query"
    return model.encode(queries, normalize_embeddings=True, convert_to_numpy=True,
                        batch_size=64, show_progress_bar=False, **kwargs).astype(np.float32)


def evaluate(index: retrieval.Index, items: list[dict], qvecs: np.ndarray | None,
             mode: str, exclude_legacy: bool) -> dict:
    # The hop mode searches legacy entries deliberately and rewrites the hits, so
    # it must not filter them out first.
    hop = mode.endswith("+hop")
    base_mode = mode[:-4] if hop else mode
    mask = index.allowed(exclude_legacy=exclude_legacy and not hop)
    kmax = max(KS)
    hits = {k: 0 for k in KS}
    per_family: dict[str, dict] = collections.defaultdict(lambda: {"n": 0, **{k: 0 for k in KS}})
    unreachable = 0
    ranks: list[int] = []

    started = time.time()
    for i, item in enumerate(items):
        gold = set(item["source_ids"])
        positions = {index.position(g) for g in gold} - {None}
        if not positions or not any(mask[p] for p in positions):
            # The gold chunk is filtered out -- a ceiling on what retrieval can do,
            # not a retrieval failure. Counted separately rather than hidden.
            unreachable += 1
            continue
        qvec = qvecs[i] if qvecs is not None else None
        pool = kmax if not hop else kmax * 2
        if base_mode == "dense":
            order = index.dense(qvec, mask, pool)
        elif base_mode == "bm25":
            order = index.lexical(item["question"], mask, pool)
        else:
            order = retrieval.rrf([index.dense(qvec, mask, 50),
                                   index.lexical(item["question"], mask, 50)], pool)
        if hop:
            order = retrieval.follow_remaster(index, order)[:kmax]
        fam = per_family[item["family"]]
        fam["n"] += 1
        found = next((r for r, idx in enumerate(order) if index.ids[idx] in gold), None)
        ranks.append(found + 1 if found is not None else 0)
        for k in KS:
            if found is not None and found < k:
                hits[k] += 1
                fam[k] += 1

    scored = sum(f["n"] for f in per_family.values())
    mrr = sum(1 / r for r in ranks if r) / scored if scored else 0.0
    return {
        "mode": mode, "model": index.model_name, "scored": scored,
        "unreachable": unreachable, "seconds": round(time.time() - started, 1),
        "recall": {str(k): hits[k] / scored if scored else 0.0 for k in KS},
        "mrr": mrr,
        "families": {f: {"n": v["n"], **{str(k): v[k] / v["n"] if v["n"] else 0.0 for k in KS}}
                     for f, v in sorted(per_family.items())},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=["Kaylebor/pf2e-codex-embed-xs"])
    ap.add_argument("--modes", nargs="*",
                    default=["bm25", "dense", "hybrid", "hybrid+hop"],
                    help="'+hop' rewrites legacy hits to their Remaster replacements")
    ap.add_argument("--benchmark", type=pathlib.Path, default=ROOT / "eval" / "benchmark.jsonl")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "eval" / "runs" / "retrieval.scores.json")
    ap.add_argument("--include-legacy", action="store_true")
    args = ap.parse_args()

    items = [orjson.loads(l) for l in args.benchmark.open("rb") if orjson.loads(l)["source_ids"]]
    print(f"{len(items)} benchmark items carry a gold chunk id")

    results = []
    lexical_modes = [m for m in args.modes if m.startswith("bm25")]
    if lexical_modes:
        index = load_index(None)
        for mode in lexical_modes:
            results.append(evaluate(index, items, None, mode, not args.include_legacy))

    for model in args.models:
        index = load_index(model)
        qvecs = encode_queries(model, [i["question"] for i in items])
        for mode in [m for m in args.modes if not m.startswith("bm25")]:
            results.append(evaluate(index, items, qvecs, mode, not args.include_legacy))

    print(f"\n{'retriever':44s} {'mode':7s} {'R@1':>6s} {'R@5':>6s} {'R@20':>6s} {'MRR':>6s}")
    print(f"{'-' * 44} {'-' * 7} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 6}")
    for r in results:
        name = r["model"] or "—"
        print(f"{name:44s} {r['mode']:7s} {r['recall']['1']:6.1%} {r['recall']['5']:6.1%} "
              f"{r['recall']['20']:6.1%} {r['mrr']:6.3f}")

    best = max(results, key=lambda r: r["recall"]["5"])
    print(f"\nbest by R@5: {best['model']} / {best['mode']}")
    print(f"  per family (R@5):")
    for fam, v in best["families"].items():
        print(f"    {fam:18s} n={v['n']:4d}  {v['5']:6.1%}")
    if results[0]["unreachable"]:
        print(f"\n  {results[0]['unreachable']} items unreachable (gold chunk filtered out)")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(orjson.dumps(results, option=orjson.OPT_INDENT_2))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
