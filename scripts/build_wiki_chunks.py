#!/usr/bin/env python3
"""Normalise data/raw/wiki/pages.jsonl into data/processed/wiki_chunks.jsonl.

One chunk per short page; long pages become a lead chunk (with the infobox as
``**Field** value`` lines) plus one chunk per section. See ``normalize.wiki_to_chunks``.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import sys

import orjson

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from kleverkobold import normalize

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=pathlib.Path, default=ROOT / "data" / "raw" / "wiki" / "pages.jsonl")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "data" / "processed" / "wiki_chunks.jsonl")
    ap.add_argument("--min-chars", type=int, default=200, help="drop stubs below this length")
    ap.add_argument("--split-at", type=int, default=2500,
                    help="pages longer than this are split into one chunk per section")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    n = pages = skipped = chars = sections = 0
    kinds: collections.Counter[str] = collections.Counter()
    with args.out.open("wb") as fh:
        for line in args.raw.open("rb"):
            page = orjson.loads(line)
            # Namespace housekeeping that slips through the API filter.
            if page["title"].split(":")[0] in ("Template", "Category", "File", "PathfinderWiki",
                                               "Help", "User", "Talk", "Module", "MediaWiki"):
                skipped += 1
                continue
            chunks = normalize.wiki_to_chunks(page, split_at=args.split_at)
            if sum(c["n_chars"] for c in chunks) < args.min_chars:
                skipped += 1
                continue
            pages += 1
            for chunk in chunks:
                fh.write(orjson.dumps(chunk))
                fh.write(b"\n")
                n += 1
                chars += chunk["n_chars"]
                sections += bool(chunk.get("section"))
                kinds[chunk["category"]] += 1

    print(f"wrote {n:,} lore chunks from {pages:,} pages ({sections:,} are sections; "
          f"{skipped:,} stubs dropped) -> {args.out}")
    print(f"  {chars / 1e6:.1f} M chars  ~= {chars / 4 / 1e6:.1f} M tokens")
    print("  top page types:", dict(kinds.most_common(8)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
