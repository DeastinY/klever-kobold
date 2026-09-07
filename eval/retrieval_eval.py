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
import os
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
REWRITES = ROOT / "data" / "processed" / "query_rewrites.json"
# 8 is the deployed excerpt count, so it is the operating point that matters;
# 5 and 20 bracket it.
KS = (1, 5, 8, 20)
DEEP_KS = (1, 8, 20, 50, 100, 200)


def remaster_partners(index: retrieval.Index, positions: set[int]) -> set[str]:
    """Chunk ids on the other side of the Remaster relation from these rows."""
    out: set[str] = set()
    for p in positions:
        meta = index.meta[p]
        for field in ("remaster_id", "legacy_id"):
            targets = meta.get(field) or []
            if isinstance(targets, str):
                targets = [targets]
            for t in targets:
                out.add(f"aon:{meta['category']}:{t}")
    return out


def load_rewrites(model: str) -> dict:
    """Cached hypothetical summaries and category hints, keyed by rewriter model."""
    if not REWRITES.exists():
        return {}
    raw = orjson.loads(REWRITES.read_bytes())
    prefix = f"{model}|"
    return {k[len(prefix):]: v for k, v in raw.items() if k.startswith(prefix)}


def load_index(model_name: str | None, want_bm25: bool = True) -> retrieval.Index:
    meta = [orjson.loads(l) for l in (INDEX / "meta.jsonl").open("rb")]
    ids = [m["id"] for m in meta]
    emb = summary = None
    if model_name:
        slug = model_name.replace("/", "__")
        path = INDEX / f"emb__{slug}.npy"
        if not path.exists():
            raise SystemExit(f"missing {path}; run scripts/build_index.py --model {model_name}")
        emb = np.load(path)
        spath = INDEX / f"emb__{slug}__summary.npy"
        if spath.exists():
            summary = np.load(spath)
    bm25 = pickle.loads((INDEX / "bm25.pkl").read_bytes()) if want_bm25 else None
    return retrieval.Index(ids=ids, meta=meta, embeddings=emb, summary_embeddings=summary,
                           bm25=bm25, model_name=model_name)


def encode_queries(model_name: str, queries: list[str]) -> np.ndarray:
    from sentence_transformers import SentenceTransformer
    # Overridable so an API run can encode on CPU without contending with a
    # training job for the GPU.
    device = os.environ.get("PF2E_EMBED_DEVICE", "cuda")
    model = SentenceTransformer(model_name, device=device)
    kwargs = {}
    # Asymmetric retrievers want the query side marked. Honour whatever the
    # checkpoint declares rather than hard-coding a prefix per family.
    if getattr(model, "prompts", None) and "query" in model.prompts:
        kwargs["prompt_name"] = "query"
    return model.encode(queries, normalize_embeddings=True, convert_to_numpy=True,
                        batch_size=64, show_progress_bar=False, **kwargs).astype(np.float32)


def evaluate(index: retrieval.Index, items: list[dict], qvecs: np.ndarray | None,
             mode: str, exclude_legacy: bool, hyde_vecs: np.ndarray | None = None,
             rewrites: dict | None = None, hyde_weight: float = 1.0,
             smoothing: int = 5, always_allow: tuple[str, ...] = ()) -> dict:
    # The hop mode searches legacy entries deliberately and rewrites the hits, so
    # it must not filter them out first.
    parts = mode.split("+")
    base_mode = parts[0]
    hop = "hop" in parts
    use_hyde = "hyde" in parts
    use_cat = "cat" in parts
    # "cat2" fuses the narrowed and unnarrowed rankings instead of replacing one
    # with the other. Narrowing sharpens entity lookup and blinds concept
    # questions; keeping both rankings costs one extra scan and no model call.
    use_both = "cat2" in parts
    # base_mask is the corpus-level filter. Query-time narrowing (category routing)
    # reassigns `mask` per item and its mistakes must count as retrieval failures,
    # not as unreachable items -- otherwise a filter that hides the answer scores
    # better than one that does not.
    base_mask = index.allowed(exclude_legacy=exclude_legacy and not hop)
    mask = base_mask
    kmax = max(KS)
    hits = {k: 0 for k in KS}
    per_family: dict[str, dict] = collections.defaultdict(lambda: {"n": 0, **{k: 0 for k in KS}})
    unreachable = 0
    ranks: list[int] = []

    started = time.time()
    for i, item in enumerate(items):
        gold = set(item["source_ids"]) | set(item.get("alt_source_ids") or [])
        # Rankings are collapsed to one row per entity, so a gold chunk that is a
        # duplicate row will never appear by id. Compare canonical positions: it is
        # the entity that has to be retrieved, not one particular copy of it.
        positions_raw = {index.position(g) for g in gold} - {None}
        # A label naming a pre-Remaster page is satisfied by the entry that
        # superseded it, and vice versa. Mined labels come from answers written
        # years ago and mostly cite legacy pages; the system deliberately returns
        # the current entry, and marking that wrong measures the label's age
        # rather than the retrieval.
        positions_raw |= {p for p in
                          (index.position(t) for t in remaster_partners(index, positions_raw))
                          if p is not None}
        gold_canon = {index.canonical[p] for p in positions_raw}
        positions = {index.position(g) for g in gold} - {None}
        if not positions or not any(base_mask[p] for p in positions):
            # Not in the index at all, or removed by the corpus-level legacy filter:
            # a ceiling on what retrieval could ever do, counted separately.
            unreachable += 1
            continue
        qvec = qvecs[i] if qvecs is not None else None
        pool = kmax if not hop else kmax * 2

        mask = base_mask
        narrow_mask = None
        if (use_cat or use_both) and rewrites:
            cats = list((rewrites.get(item["question"]) or {}).get("categories") or [])
            # Categories that answer a *concept* question. The rewriter names entry
            # kinds -- feat, spell, action -- and narrowing to them excludes the
            # rules chapters entirely, which is where questions like "is a critical
            # failure a failure?" are answered.
            cats += [c for c in always_allow if c not in cats]
            if cats:
                # Narrow to the kinds of entry that could answer this. Equipment and
                # creatures are two thirds of the corpus and answer almost nothing.
                narrowed = base_mask & index.allowed(
                    exclude_legacy=exclude_legacy and not hop, categories=cats)
                if narrowed.sum() >= kmax:
                    if use_both:
                        narrow_mask = narrowed
                    else:
                        mask = narrowed
        if base_mode == "dense":
            order = index.dense(qvec, mask, pool)
        elif base_mode == "summary":
            order = index.dense(qvec, mask, pool, view="summary")
        elif base_mode == "bm25":
            order = index.lexical(item["question"], mask, pool)
        elif base_mode == "hybrid3":
            # bm25 + full-text dense + summary dense. The three views fail on
            # different question shapes, which is the whole point of fusing them.
            rankings = [index.dense(qvec, mask, 50),
                        index.dense(qvec, mask, 50, view="summary"),
                        index.lexical(item["question"], mask, 50)]
            weights = [1.0, 1.0, 1.0]
            if use_hyde and hyde_vecs is not None:
                # The generated summary is matched against the summary index: both
                # sides of that comparison are one-line descriptions.
                rankings.append(index.dense(hyde_vecs[i], mask, 50, view="summary"))
                rankings.append(index.dense(hyde_vecs[i], mask, 50))
                weights += [hyde_weight, hyde_weight]
            if narrow_mask is not None:
                rankings.append(index.dense(qvec, narrow_mask, 50))
                rankings.append(index.dense(qvec, narrow_mask, 50, view="summary"))
                rankings.append(index.lexical(item["question"], narrow_mask, 50))
                weights += [1.0, 1.0, 1.0]
                if use_hyde and hyde_vecs is not None:
                    rankings.append(index.dense(hyde_vecs[i], narrow_mask, 50, view="summary"))
                    weights += [hyde_weight]
            order = retrieval.rrf(rankings, pool, smoothing, weights=weights, index=index)
        else:
            order = retrieval.rrf([index.dense(qvec, mask, 50),
                                   index.lexical(item["question"], mask, 50)], pool, index=index)
        if hop:
            order = retrieval.follow_remaster(index, order)
        order = retrieval.dedupe(index, order)[:kmax]
        fam = per_family[item["family"]]
        fam["n"] += 1
        found = next((r for r, idx in enumerate(order)
                      if index.canonical[idx] in gold_canon), None)
        ranks.append(found + 1 if found is not None else 0)
        for k in KS:
            if found is not None and found < k:
                hits[k] += 1
                fam[k] += 1

    scored = sum(f["n"] for f in per_family.values())
    mrr = sum(1 / r for r in ranks if r) / scored if scored else 0.0
    return {
        "mode": mode, "model": index.model_name, "scored": scored,
        "hyde_weight": hyde_weight, "smoothing": smoothing,
        "always_allow": list(always_allow),
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
    ap.add_argument("--deep", action="store_true",
                    help="report a deep recall curve; a curve that stays flat means the gold "
                         "is not findable at all, which is a label problem, not a ranking one")
    ap.add_argument("--always-allow", nargs="*", default=[[]], action="append",
                    help="categories never excluded by narrowing; repeat to sweep")
    ap.add_argument("--smoothing", nargs="*", type=int, default=[5],
                    help="RRF constant; 60 is the TREC default and is far too flat here")
    ap.add_argument("--hyde-weights", nargs="*", type=float, default=[1.0],
                    help="sweep the weight given to the hypothetical-summary rankings")
    ap.add_argument("--rewriter", default="Qwen/Qwen3.8-27B",
                    help="which cached rewrite set to use for +hyde / +cat modes")
    args = ap.parse_args()

    items = [orjson.loads(l) for l in args.benchmark.open("rb")
             if orjson.loads(l)["source_ids"] and not orjson.loads(l).get("excluded")]
    print(f"{len(items)} benchmark items carry a gold chunk id")

    results = []
    lexical_modes = [m for m in args.modes if m.startswith("bm25")]
    if lexical_modes:
        index = load_index(None)
        for mode in lexical_modes:
            results.append(evaluate(index, items, None, mode, not args.include_legacy))

    rewrites = load_rewrites(args.rewriter)
    needs_hyde = any("hyde" in m for m in args.modes)
    if needs_hyde and not rewrites:
        raise SystemExit(f"no cached rewrites for {args.rewriter}; run scripts/rewrite_queries.py")

    for model in args.models:
        index = load_index(model)
        qvecs = encode_queries(model, [i["question"] for i in items])
        hyde_vecs = None
        if needs_hyde:
            hyde_vecs = encode_queries(
                model, [(rewrites.get(i["question"]) or {}).get("summary") or i["question"]
                        for i in items])
        for mode in [m for m in args.modes if not m.startswith("bm25")]:
            for w in (args.hyde_weights if "hyde" in mode else [1.0]):
                for sm in args.smoothing:
                    for aa in args.always_allow:
                        results.append(evaluate(index, items, qvecs, mode,
                                                not args.include_legacy, hyde_vecs,
                                                rewrites, w, sm, tuple(aa)))

    print(f"\n{'retriever':32s} {'mode':26s} {'R@1':>6s} {'R@5':>6s} {'R@8':>6s} {'R@20':>6s} {'MRR':>6s}")
    print(f"{'-' * 32} {'-' * 26} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 6}")
    for r in results:
        name = r["model"] or "—"
        aa = "+".join(r.get("always_allow") or []) or "none"
        tag = f"{r['mode']} keep={aa}"
        print(f"{name:32s} {tag:26s} {r['recall']['1']:6.1%} {r['recall']['5']:6.1%} "
              f"{r['recall']['8']:6.1%} {r['recall']['20']:6.1%} {r['mrr']:6.3f}")

    best = max(results, key=lambda r: r["recall"]["8"])
    print(f"\nbest by R@8: {best['model']} / {best['mode']}")
    print(f"  per family (R@8):")
    for fam, v in best["families"].items():
        print(f"    {fam:18s} n={v['n']:4d}  {v['8']:6.1%}")
    unreachable = {(r["mode"], r["unreachable"]) for r in results if r["unreachable"]}
    for mode, n in sorted(unreachable):
        print(f"  {n} unreachable in {mode} (gold removed by the corpus filter)")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(orjson.dumps(results, option=orjson.OPT_INDENT_2))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
