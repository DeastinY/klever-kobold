"""Command line and MCP entry points.

    python -m pf2etune ask "can my level 4 fighter take Power Attack?"
    python -m pf2etune search "a feat that makes falling less dangerous"
    python -m pf2etune doctor          # check Ollama, models, index
    python -m pf2etune mcp             # stdio MCP server
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import orjson

from .app import DEFAULT_INDEX, DEFAULT_K, DEFAULT_OLLAMA, Assistant, Ollama, OllamaError


def cmd_ask(args) -> int:
    a = Assistant(args.index, args.ollama)
    result = a.ask(args.question, k=args.k, rerank=not args.no_rerank)
    if args.json:
        sys.stdout.write(orjson.dumps(result, option=orjson.OPT_INDENT_2).decode() + "\n")
        return 0
    print(result["answer"])
    print("\nsources:")
    for s in result["sources"]:
        print(f"  {s['name']} ({s['category']}) — {s['url']}")
    return 0


def cmd_search(args) -> int:
    a = Assistant(args.index, args.ollama)
    plan = a.rewrite(args.question)
    hits = a.search(args.question, k=args.k, plan=plan, rerank=not args.no_rerank)
    print(f"interpreted as: {plan['summary']!r}  kinds={plan['categories']}\n")
    for n, h in enumerate(hits, 1):
        level = f" (level {h.level})" if h.level is not None else ""
        print(f"{n}. {h.name} [{h.category}]{level}\n   {h.url}")
    return 0


def cmd_doctor(args) -> int:
    """Check every moving part separately, so a failure names itself."""
    ok = True
    index = pathlib.Path(args.index)
    print(f"index      {index}")
    for name in ("manifest.json", "meta.jsonl", "bodies.jsonl", "emb_full.npy",
                 "emb_summary.npy", "bm25.npz"):
        path = index / name
        mark = "ok  " if path.exists() else "MISSING"
        size = f"{path.stat().st_size / 1e6:.0f} MB" if path.exists() else ""
        print(f"  {mark} {name:18s} {size}")
        ok &= path.exists()
    if not ok:
        print("\n-> unpack pf2e-index next to the package, or pass --index")
        return 1

    manifest = orjson.loads((index / "manifest.json").read_bytes())
    client = Ollama(args.ollama)
    for key in ("ollama_embed", "ollama_llm"):
        model = manifest[key]
        try:
            if key == "ollama_embed":
                client.embed(["ping"], model)
            else:
                client.chat("Reply with the single word: ok", "ping", model, max_tokens=8)
            print(f"  ok   {key:18s} {model}")
        except OllamaError as exc:
            print(f"  FAIL {key:18s} {model}\n       {exc}")
            ok = False

    if ok:
        a = Assistant(args.index, args.ollama)
        hits = a.search("a feat that makes falling less dangerous", k=3)
        names = ", ".join(h.name for h in hits)
        print(f"\n  retrieval smoke test -> {names}")
        print("\nall good.")
    return 0 if ok else 1


def cmd_mcp(args) -> int:
    from .mcp_server import serve
    serve(args.index, args.ollama)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pf2etune", description="Pathfinder 2e rules assistant")
    ap.add_argument("--index", type=pathlib.Path, default=DEFAULT_INDEX)
    ap.add_argument("--ollama", default=DEFAULT_OLLAMA)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ask", help="answer a rules question with citations")
    p.add_argument("question")
    p.add_argument("-k", type=int, default=DEFAULT_K)
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-rerank", action="store_true",
                   help="skip the listwise rerank; slightly faster, worse on hard questions")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("search", help="show what retrieval finds, without answering")
    p.add_argument("question")
    p.add_argument("-k", type=int, default=DEFAULT_K)
    p.add_argument("--no-rerank", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("doctor", help="check Ollama, models and index")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("mcp", help="run as an MCP server over stdio")
    p.set_defaults(func=cmd_mcp)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except OllamaError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
