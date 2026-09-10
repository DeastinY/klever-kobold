#!/usr/bin/env python3
"""Dump the full Archives of Nethys index to data/raw/aon/<category>.jsonl."""

from __future__ import annotations

import argparse
import pathlib
import sys

import httpx
import orjson

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from kleverkobold import aon  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[1] / "data" / "raw" / "aon"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path, default=OUT)
    ap.add_argument("--only", nargs="*", help="restrict to these categories")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    with httpx.Client(headers={"User-Agent": "kleverkobold/0.1 (research corpus build)"}) as client:
        total = aon.total_documents(client)
        cats = aon.categories(client)
        if args.only:
            cats = [c for c in cats if c.name in set(args.only)]
        print(f"index holds {total:,} documents across {len(cats)} categories")

        manifest, written = {}, 0
        for cat in sorted(cats, key=lambda c: -c.count):
            path = args.out / f"{cat.name}.jsonl"
            n = 0
            with path.open("wb") as fh:
                for doc in aon.fetch_category(client, cat.name):
                    fh.write(orjson.dumps(doc))
                    fh.write(b"\n")
                    n += 1
            manifest[cat.name] = {"expected": cat.count, "written": n}
            written += n
            flag = "" if n == cat.count else f"  !! expected {cat.count}"
            print(f"  {cat.name:24s} {n:6,d}{flag}")

        (args.out / "_manifest.json").write_bytes(
            orjson.dumps(
                {"source": aon.ES_URL, "index": aon.INDEX, "total": total, "categories": manifest},
                option=orjson.OPT_INDENT_2,
            )
        )
    print(f"wrote {written:,} documents to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
