#!/usr/bin/env python3
"""Normalise data/raw/wiki/pages.jsonl into data/processed/wiki_chunks.jsonl."""

from __future__ import annotations

import argparse
import collections
import pathlib
import sys

import orjson

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from kleverkobold import normalize  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=pathlib.Path, default=ROOT / "data" / "raw" / "wiki" / "pages.jsonl")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "data" / "processed" / "wiki_chunks.jsonl")
    ap.add_argument("--min-chars", type=int, default=200, help="drop stubs below this length")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    n = skipped = chars = 0
    kinds: collections.Counter[str] = collections.Counter()
    with args.out.open("wb") as fh:
        for line in args.raw.open("rb"):
            chunk = normalize.wiki_to_chunk(orjson.loads(line))
            if chunk["n_chars"] < args.min_chars:
                skipped += 1
                continue
            fh.write(orjson.dumps(chunk))
            fh.write(b"\n")
            n += 1
            chars += chunk["n_chars"]
            kinds[chunk["category"]] += 1

    print(f"wrote {n:,} lore chunks ({skipped:,} stubs dropped) -> {args.out}")
    print(f"  {chars / 1e6:.1f} M chars  ~= {chars / 4 / 1e6:.1f} M tokens")
    print("  top page types:", dict(kinds.most_common(8)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
