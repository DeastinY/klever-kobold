#!/usr/bin/env python3
"""Normalise data/raw/aon/*.jsonl into data/processed/aon_chunks.jsonl."""

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
    ap.add_argument("--raw", type=pathlib.Path, default=ROOT / "data" / "raw" / "aon")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "data" / "processed" / "aon_chunks.jsonl")
    ap.add_argument("--keep-hidden", action="store_true", help="keep exclude_from_search entries")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    n = skipped = chars = links = 0
    by_status: collections.Counter[str] = collections.Counter()
    by_cat: collections.Counter[str] = collections.Counter()

    # First pass: what every entry is called, so a parent can name the entries
    # AoN embeds in it (a rules page's activities, a creature's abilities).
    lookup: dict[str, dict] = {}
    for path in sorted(args.raw.glob("*.jsonl")):
        for line in path.open("rb"):
            doc = orjson.loads(line)
            if doc.get("id"):
                lookup[doc["id"]] = normalize.embed_lookup_entry(doc)

    with args.out.open("wb") as fh:
        for path in sorted(args.raw.glob("*.jsonl")):
            for line in path.open("rb"):
                chunk = normalize.resolve_embeds(normalize.to_chunk(orjson.loads(line)), lookup)
                chunk = normalize.fill_legacy_name(chunk, lookup)
                if chunk["hidden"] and not args.keep_hidden:
                    skipped += 1
                    continue
                if not chunk["text"]:
                    skipped += 1
                    continue
                fh.write(orjson.dumps(chunk))
                fh.write(b"\n")
                n += 1
                chars += chunk["n_chars"]
                links += len(chunk["links"])
                by_status[chunk["remaster_status"]] += 1
                by_cat[chunk["category"]] += 1

    print(f"wrote {n:,} chunks ({skipped:,} skipped) -> {args.out}")
    print(f"  {chars / 1e6:.1f} M chars  ~= {chars / 4 / 1e6:.1f} M tokens")
    print(f"  {links:,} outbound entity links  ({links / max(n, 1):.1f} per chunk)")
    print("  remaster status:", dict(by_status))
    print("  top categories:", dict(by_cat.most_common(8)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
