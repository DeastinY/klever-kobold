#!/usr/bin/env python3
"""Build the self-contained index a laptop needs, and nothing more.

The development index is 563 MB of float32 across five embedders. A deployment
needs one embedder, half the precision, and no pickles. This writes
``dist/pf2e-index/`` -- roughly 270 MB, loadable by memory-map in under a second,
with no torch, no transformers, and no CUDA anywhere in the dependency graph.

float16 halves the embeddings at no measurable cost to ranking: cosine
similarity over unit vectors is dominated by direction, and the quantisation
error here is ~1e-3 against inter-document distances of ~0.3.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import sys

import numpy as np
import orjson

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pf2etune import retrieval  # noqa: E402
from pf2etune.bm25 import BM25  # noqa: E402

META_FIELDS = ("id", "name", "category", "level", "traits", "rarity", "book",
               "remaster_status", "remaster_id", "url", "summary")

# Qwen3-Embedding asks for queries to be marked. Ollama will not add this, so the
# runtime prepends it by hand; it lives in the manifest so the two cannot drift.
QUERY_PREFIX = ("Instruct: Given a web search query, retrieve relevant passages "
                "that answer the query\nQuery:")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "aon_chunks.jsonl")
    ap.add_argument("--index", type=pathlib.Path, default=ROOT / "data" / "processed" / "index")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "dist" / "pf2e-index")
    ap.add_argument("--embed-model", default="Qwen/Qwen3-Embedding-0.6B")
    ap.add_argument("--ollama-embed", default="qwen3-embedding:0.6b")
    ap.add_argument("--ollama-llm", default="qwen3.5:9b")
    ap.add_argument("--body-chars", type=int, default=2400,
                    help="truncate entry bodies; the longest are class tables nobody quotes")
    args = ap.parse_args()

    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)

    rows = [orjson.loads(l) for l in args.chunks.open("rb")]
    print(f"{len(rows):,} chunks")

    with (args.out / "meta.jsonl").open("wb") as fh:
        for r in rows:
            fh.write(orjson.dumps({k: r.get(k) for k in META_FIELDS}))
            fh.write(b"\n")
    with (args.out / "bodies.jsonl").open("wb") as fh:
        for r in rows:
            fh.write(orjson.dumps({"id": r["id"], "text": (r["text"] or "")[:args.body_chars]}))
            fh.write(b"\n")

    slug = args.embed_model.replace("/", "__")
    for src, dst in ((f"emb__{slug}.npy", "emb_full.npy"),
                     (f"emb__{slug}__summary.npy", "emb_summary.npy")):
        path = args.index / src
        if not path.exists():
            raise SystemExit(f"missing {path}")
        vecs = np.load(path).astype(np.float16)
        np.save(args.out / dst, vecs)
        print(f"  {dst}: {vecs.shape} float16")

    # The outbound link graph: a topic page cites the specific rule, and
    # interaction questions need the latter.
    import re as _re
    RE_ID = _re.compile(r"/([A-Za-z]+)\.aspx\?ID=(\d+)", _re.I)

    def page_key(url: str) -> str | None:
        m = RE_ID.search(url or "")
        return f"{m.group(1).lower()}:{m.group(2)}" if m else None

    by_page: dict[str, str] = {}
    for r in rows:
        k = page_key(r.get("url"))
        if k and (k not in by_page or r["remaster_status"] != "legacy"):
            by_page[k] = r["id"]
    edges = 0
    with (args.out / "links.jsonl").open("wb") as fh:
        for r in rows:
            targets = []
            for link in (r.get("links") or []):
                k = page_key(link.get("url"))
                t = by_page.get(k) if k else None
                if t and t != r["id"] and t not in targets:
                    targets.append(t)
            if targets:
                fh.write(orjson.dumps({"id": r["id"], "to": targets[:24]}))
                fh.write(b"\n")
                edges += len(targets[:24])
    print(f"  links.jsonl: {edges:,} edges")

    bm25_path = args.index / "bm25.npz"
    if not bm25_path.exists():
        print("  building bm25...")
        BM25.build([retrieval.tokenize(retrieval.chunk_text(r)) for r in rows]).save(bm25_path)
    shutil.copy(bm25_path, args.out / "bm25.npz")

    (args.out / "manifest.json").write_bytes(orjson.dumps({
        "version": 1,
        "chunks": len(rows),
        "embed_model": args.embed_model,
        "ollama_embed": args.ollama_embed,
        "ollama_llm": args.ollama_llm,
        "query_prefix": QUERY_PREFIX,
        "retrieval_mode": "hybrid3+hyde+cat+hop",
        "source": "Archives of Nethys (https://2e.aonprd.com/)",
        "notice": ("This work uses trademarks and/or copyrights owned by Paizo Inc., "
                   "used under Paizo's Community Use Policy "
                   "(https://paizo.com/communityuse). We are expressly prohibited from "
                   "charging you to use or access this content. This work is not "
                   "published, endorsed, or specifically approved by Paizo. For more "
                   "information about Paizo Inc. and Paizo products, visit paizo.com."),
        "licence": "Rules mechanics under the ORC License and OGL v1.0a; "
                   "setting material under Paizo's Community Use Policy. "
                   "Non-commercial use only.",
    }, option=orjson.OPT_INDENT_2))

    total = sum(p.stat().st_size for p in args.out.iterdir())
    print(f"\nwrote {args.out}  ({total / 1e6:.0f} MB)")
    for p in sorted(args.out.iterdir(), key=lambda p: -p.stat().st_size):
        print(f"  {p.stat().st_size / 1e6:7.1f} MB  {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
