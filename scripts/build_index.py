#!/usr/bin/env python3
"""Embed the corpus and cache a retrieval index under data/processed/index/."""

from __future__ import annotations

import argparse
import pathlib
import pickle
import sys
import time

import numpy as np
import orjson

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pf2etune import retrieval  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"

META_FIELDS = ("id", "name", "category", "level", "traits", "rarity", "book",
               "remaster_status", "remaster_id", "legacy_id", "legacy_name", "url", "summary")


def slug(model_name: str) -> str:
    return model_name.replace("/", "__")


def summary_text(chunk: dict) -> str:
    """Name plus the one-line summary, and nothing else.

    The full-text index buries an entry's *purpose* under its mechanics. A
    description-shaped query ("a feat that makes falling less dangerous") matches
    the summary almost verbatim and the body barely at all, so the two indexes
    fail on different questions and fuse well.
    """
    head = chunk.get("name") or ""
    if chunk.get("category"):
        head += f" ({chunk['category'].replace('-', ' ')})"
    return f"{head}: {chunk.get('summary') or ''}".strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Kaylebor/pf2e-codex-embed-xs")
    ap.add_argument("--chunks", type=pathlib.Path, default=PROC / "aon_chunks.jsonl")
    ap.add_argument("--out", type=pathlib.Path, default=PROC / "index")
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--max-chars", type=int, default=1200)
    ap.add_argument("--bm25-only", action="store_true")
    ap.add_argument("--field", choices=("full", "summary"), default="full",
                    help="what to embed: the whole entry, or name + one-line summary")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    rows = [orjson.loads(l) for l in args.chunks.open("rb")]
    if args.field == "summary":
        texts = [summary_text(r) for r in rows]
    else:
        texts = [retrieval.chunk_text(r, args.max_chars) for r in rows]
    meta = [{k: r.get(k) for k in META_FIELDS} for r in rows]
    ids = [r["id"] for r in rows]
    print(f"{len(rows):,} chunks, mean {sum(map(len, texts)) / len(texts):.0f} chars")

    # BM25 is model-independent, so build it once and share it across embedders.
    bm25_path = args.out / "bm25.pkl"
    if not bm25_path.exists():
        from rank_bm25 import BM25Okapi
        started = time.time()
        bm25 = BM25Okapi([retrieval.tokenize(t) for t in texts])
        bm25_path.write_bytes(pickle.dumps(bm25))
        print(f"built bm25 in {time.time() - started:.0f}s -> {bm25_path}")
    else:
        print(f"reusing {bm25_path}")

    meta_path = args.out / "meta.jsonl"
    if True:  # cheap; always rewrite so metadata cannot drift from META_FIELDS
        with meta_path.open("wb") as fh:
            for m in meta:
                fh.write(orjson.dumps(m))
                fh.write(b"\n")

    if args.bm25_only:
        return 0

    from sentence_transformers import SentenceTransformer
    started = time.time()
    model = SentenceTransformer(args.model, device="cuda")
    vecs = model.encode(texts, batch_size=args.batch_size, normalize_embeddings=True,
                        convert_to_numpy=True, show_progress_bar=True).astype(np.float32)
    suffix = "" if args.field == "full" else f"__{args.field}"
    path = args.out / f"emb__{slug(args.model)}{suffix}.npy"
    np.save(path, vecs)
    print(f"embedded {len(ids):,} chunks in {time.time() - started:.0f}s "
          f"-> {path} {vecs.shape} ({vecs.nbytes / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
