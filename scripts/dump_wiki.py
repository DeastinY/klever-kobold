#!/usr/bin/env python3
"""Dump PathfinderWiki article wikitext to data/raw/wiki/pages.jsonl."""

from __future__ import annotations

import argparse
import pathlib
import sys

import httpx
import orjson

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pf2etune import wiki  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[1] / "data" / "raw" / "wiki"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path, default=OUT)
    ap.add_argument("--limit", type=int, help="stop after N pages (for smoke tests)")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    with httpx.Client(headers={"User-Agent": wiki.UA}) as client:
        info = wiki.site_info(client)
        stats = info["statistics"]
        print(f"wiki reports {stats['articles']:,} articles, {stats['pages']:,} pages")
        print(f"rights: {info['rightsinfo']['text']}")

        path = args.out / "pages.jsonl"
        n = chars = 0
        with path.open("wb") as fh:
            for page in wiki.iter_pages(client):
                fh.write(orjson.dumps(page))
                fh.write(b"\n")
                n += 1
                chars += len(page["wikitext"])
                if n % 1000 == 0:
                    print(f"  {n:6,d} pages  {chars / 1e6:6.1f} M chars", flush=True)
                if args.limit and n >= args.limit:
                    break

        (args.out / "_manifest.json").write_bytes(
            orjson.dumps(
                {"source": wiki.API, "rights": info["rightsinfo"], "statistics": stats,
                 "pages_written": n, "chars": chars},
                option=orjson.OPT_INDENT_2,
            )
        )
    print(f"wrote {n:,} pages ({chars / 1e6:.1f} M chars) to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
