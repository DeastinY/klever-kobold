#!/usr/bin/env python3
"""Summarise the built corpus into data/processed/corpus_stats.json."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import pathlib

import orjson

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"


def summarise(path: pathlib.Path) -> dict:
    n = chars = links = 0
    cats: collections.Counter[str] = collections.Counter()
    status: collections.Counter[str] = collections.Counter()
    for line in path.open("rb"):
        row = orjson.loads(line)
        n += 1
        chars += row.get("n_chars", 0)
        cats[row.get("category", "?")] += 1
        links += len(row.get("links") or ())
        if row.get("remaster_status"):
            status[row["remaster_status"]] += 1
    return {
        "documents": n,
        "chars": chars,
        "approx_tokens": round(chars / 4),
        "outbound_links": links,
        "categories": dict(cats.most_common()),
        "remaster_status": dict(status),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path, default=PROC / "corpus_stats.json")
    args = ap.parse_args()

    stats = {"generated": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
    for key, name in (("aon", "aon_chunks.jsonl"), ("pathfinderwiki", "wiki_chunks.jsonl")):
        path = PROC / name
        if path.exists():
            stats[key] = summarise(path)

    bench = ROOT / "eval" / "benchmark.jsonl"
    if bench.exists():
        fams: collections.Counter[str] = collections.Counter()
        total = 0
        for line in bench.open("rb"):
            fams[orjson.loads(line)["family"]] += 1
            total += 1
        stats["benchmark"] = {"items": total, "families": dict(fams.most_common())}

    total_tokens = sum(stats[k]["approx_tokens"] for k in ("aon", "pathfinderwiki") if k in stats)
    stats["total_approx_tokens"] = total_tokens

    args.out.write_bytes(orjson.dumps(stats, option=orjson.OPT_INDENT_2))
    print(f"wrote {args.out}")
    for key in ("aon", "pathfinderwiki"):
        if key in stats:
            s = stats[key]
            print(f"  {key:16s} {s['documents']:7,d} docs  {s['approx_tokens'] / 1e6:5.1f} M tokens")
    print(f"  {'TOTAL':16s} {'':7s}       {total_tokens / 1e6:5.1f} M tokens")
    if "benchmark" in stats:
        print(f"  benchmark        {stats['benchmark']['items']:7,d} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
