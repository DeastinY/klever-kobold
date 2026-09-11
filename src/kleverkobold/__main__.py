"""Command line and MCP entry points.

    kobold setup                         # pull models, fetch the index
    kobold serve                         # web UI on localhost:8765
    kobold ask "can my level 4 fighter take Power Attack?"

Equivalently, without installing: uv run --with kleverkobold pf2e ...

    python -m kleverkobold ask "can my level 4 fighter take Power Attack?"
    python -m kleverkobold search "a feat that makes falling less dangerous"
    python -m kleverkobold serve           # web UI on localhost:8765
    python -m kleverkobold doctor          # check Ollama, models, index
    python -m kleverkobold mcp             # stdio MCP server
"""

from __future__ import annotations

import argparse
import os
import pathlib
import shutil
import subprocess
import sys
import time

import orjson

from .app import (DEFAULT_INDEX, DEFAULT_K, DEFAULT_OLLAMA, DEFAULT_SCOPE, SCOPES, Assistant,
                  Ollama, OllamaError, Turn, default_llm)


def _llm(args) -> tuple[str | None, bool]:
    """The answering model to use: the override, else the one this machine should run.

    Returns (model, auto): `auto` says the machine picked it, so the caller can
    say so once -- a 16 GB laptop silently running the 4B would look like a
    quality bug to anyone who read the README's 9B numbers.
    """
    override = getattr(args, "llm_override", None)
    if override or getattr(args, "backend", "ollama") != "ollama":
        return override, False
    model, why = default_llm()
    print(f"answering model  {why}", file=sys.stderr)
    return model, True


def _assistant(args) -> Assistant:
    model, _ = _llm(args)
    return Assistant(args.index, args.ollama, backend=args.backend, llm_model=model,
                     embed_model=getattr(args, "embed_override", None))


def cmd_ask(args) -> int:
    a = _assistant(args)
    if args.json:
        result = a.ask(args.question, k=args.k, rerank=not args.no_rerank, scope=args.scope)
        result.pop("hits", None)   # Hit bodies would bloat the JSON; sources cover it
        sys.stdout.write(orjson.dumps(result, option=orjson.OPT_INDENT_2).decode() + "\n")
        return 0

    # Streamed, because on a laptop the answer decodes at reading speed and a
    # silent terminal for half a minute is indistinguishable from a hang.
    sources, timings = [], {}
    for event in a.ask_stream(args.question, k=args.k, rerank=not args.no_rerank,
                              scope=args.scope):
        if event["event"] == "sources":
            sources = event["sources"]
            if event.get("scope") == "lore":
                print("(answering from Golarion lore as well as the rules)\n", file=sys.stderr)
        elif event["event"] == "token":
            sys.stdout.write(event["text"])
            sys.stdout.flush()
        elif event["event"] == "done":
            timings = event["timings"]
    print("\n\nsources:")
    for s in sources:
        lore = ", lore" if s.get("corpus") == "pathfinderwiki" else ""
        print(f"  {s['name']} ({s['category']}{lore}) — {s['url']}")
    if args.timings:
        parts = " · ".join(f"{k.replace('_', ' ')} {v:.1f}s" for k, v in timings.items())
        print(f"\n{parts}", file=sys.stderr)
    return 0


def cmd_chat(args) -> int:
    """`ask`, but each question may lean on the one before it.

    A separate command rather than a flag on `ask`, because `ask` is one shot
    and has nowhere to keep a turn. Everything else is the same pipeline; the
    only difference is that a follow-up is condensed into a question that can
    be looked up before retrieval sees it, and that the condensed form is
    printed -- when a follow-up goes wrong, that line is nearly always where.
    """
    a = _assistant(args)
    print("A conversation with the kobold. Each question may refer to the last one.\n"
          "  /new    forget the thread and start fresh\n"
          "  ctrl-d  stop\n", file=sys.stderr)
    history: list[Turn] = []
    while True:
        try:
            question = input("\nyou > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not question:
            continue
        if question in ("/new", "/fresh"):
            history.clear()
            print("  (fresh thread)", file=sys.stderr)
            continue
        if question in ("/quit", "/exit"):
            return 0

        sources, timings, pieces, standalone = [], {}, [], ""
        # Only the last turn is carried. The turn holds its own condensed form,
        # so a third question still finds its way back to the first subject.
        for event in a.ask_stream(question, k=args.k, rerank=not args.no_rerank,
                                  history=history[-1:] or None):
            if event["event"] == "sources":
                sources = event["sources"]
                standalone = event["plan"].get("standalone", "")
                if standalone and standalone != question:
                    print(f"  (read as: {standalone})", file=sys.stderr)
                print("\nkobold> ", end="", flush=True)
            elif event["event"] == "token":
                pieces.append(event["text"])
                sys.stdout.write(event["text"])
                sys.stdout.flush()
            elif event["event"] == "done":
                timings = event["timings"]
        answer = "".join(pieces).strip()
        print("\n\nsources:")
        for s in sources:
            print(f"  {s['name']} ({s['category']}) — {s['url']}")
        if args.timings:
            parts = " · ".join(f"{k.replace('_', ' ')} {v:.1f}s" for k, v in timings.items())
            print(f"\n{parts}", file=sys.stderr)
        history.append(Turn(question=question, answer=answer, standalone=standalone))


def cmd_search(args) -> int:
    a = _assistant(args)
    plan = a.rewrite(args.question)
    hits = a.search(args.question, k=args.k, plan=plan, rerank=not args.no_rerank,
                    scope=args.scope)
    scope = "lore" if a.resolve_scope(args.scope, plan) else "rules"
    print(f"interpreted as: {plan['summary']!r}  kinds={plan['categories']}  scope={scope}\n")
    for n, h in enumerate(hits, 1):
        level = f" (level {h.level})" if h.level is not None else ""
        lore = ", lore" if h.lore else ""
        print(f"{n}. {h.name} [{h.category}{lore}]{level}\n   {h.url}")
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
        print("\n-> unpack kobold-index next to the package, or pass --index")
        return 1

    manifest = orjson.loads((index / "manifest.json").read_bytes())
    if args.backend == "ollama":
        try:
            import httpx
            version = httpx.get(f"{args.ollama.rstrip('/')}/api/version",
                                timeout=5.0).json().get("version", "?")
            note = ""
            if sys.platform == "darwin":
                parts = version.split(".")
                try:
                    recent = (int(parts[0]), int(parts[1])) >= (0, 19)
                except (ValueError, IndexError):
                    recent = False
                note = ("  — uses MLX on Apple Silicon" if recent
                        else "  — older than 0.19, so still on the llama.cpp Metal "
                             "backend; upgrading roughly doubles decode speed")
            print(f"  ok   ollama version     {version}{note}")
        except Exception:
            pass
    if args.backend == "ollama" and not shutil.which("ollama"):
        hint = INSTALL_HINT.get(
            "linux" if sys.platform.startswith("linux") else sys.platform,
            "See https://ollama.com/download")
        print(f"\n  Ollama is not installed.\n  {hint}\n  Then: kobold setup")
        return 1
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
        a = _assistant(args)
        by_corpus = manifest.get("chunks_by_corpus") or {"aon": manifest.get("chunks")}
        print("  ok   corpus             " + ", ".join(f"{v:,} {k}" for k, v in by_corpus.items())
              + ("" if a.has_lore else "  (no lore in this index)"))
        hits = a.search("a feat that makes falling less dangerous", k=3)
        names = ", ".join(h.name for h in hits)
        print(f"\n  retrieval smoke test -> {names}")
        if a.has_lore:
            hits = a.search("Who rules Cheliax?", k=3, scope="lore")
            print(f"  lore smoke test      -> {', '.join(h.name for h in hits)}")
        print("\nall good.")
    return 0 if ok else 1


SCOPE_HELP = ("what to answer from: 'rules' is the Archives of Nethys alone, 'lore' adds "
              "PathfinderWiki, 'auto' (default) decides per question and never gives a "
              "rules question lore")

INSTALL_HINT = {
    "darwin": "brew install ollama\n  or download the app from https://ollama.com/download",
    "linux": "curl -fsSL https://ollama.com/install.sh | sh",
    "win32": "winget install Ollama.Ollama\n  or download from https://ollama.com/download",
}


def install_ollama() -> bool:
    """Run the official installer. Only ever from --install-ollama."""
    if sys.platform == "darwin":
        if shutil.which("brew"):
            return subprocess.call(["brew", "install", "ollama"]) == 0
        print("  Homebrew not found. Download the app: https://ollama.com/download",
              file=sys.stderr)
        return False
    if sys.platform.startswith("linux"):
        print("  running the official installer (it will ask for sudo)")
        return subprocess.call(
            "curl -fsSL https://ollama.com/install.sh | sh", shell=True) == 0
    print("  Automatic install is not supported here. See https://ollama.com/download",
          file=sys.stderr)
    return False


def ensure_ollama(url: str, install: bool) -> bool:
    """Make sure Ollama is installed and answering, or explain precisely why not.

    Installing is opt-in because it modifies the system. Starting an
    already-installed server is not, because that is plainly what someone running
    `kobold setup` is asking for -- and it is the step people most often miss.
    """
    import httpx

    def up() -> bool:
        try:
            httpx.get(f"{url.rstrip('/')}/api/tags", timeout=3.0)
            return True
        except httpx.HTTPError:
            return False

    if up():
        return True

    if not shutil.which("ollama"):
        if install:
            print("ollama    not installed — installing", flush=True)
            if not install_ollama():
                return False
        else:
            hint = INSTALL_HINT.get(
                "linux" if sys.platform.startswith("linux") else sys.platform,
                "See https://ollama.com/download")
            print(f"ollama    not installed.\n\n  {hint}\n\n"
                  f"  Then re-run `kobold setup`, or `kobold setup --install-ollama` to have "
                  f"this do it.", file=sys.stderr)
            return False

    # Installed but not answering. Only start one if the caller is asking for the
    # default endpoint: someone who passed --ollama http://host:9999 wants *that*
    # server, and launching a local one on 11434 would not help them.
    if url.rstrip("/") == DEFAULT_OLLAMA:
        print("ollama    installed but not running — starting it", flush=True)
        try:
            subprocess.Popen(["ollama", "serve"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        except OSError as exc:
            print(f"  could not start it: {exc}", file=sys.stderr)
            return False
        for _ in range(30):
            time.sleep(1)
            if up():
                print("  ok   running", flush=True)
                return True
        print("  it did not come up. Try `ollama serve` in another terminal.",
              file=sys.stderr)
        return False

    print(f"ollama    installed, but nothing is answering at {url}.\n"
          f"  Start it there, or drop --ollama to use {DEFAULT_OLLAMA}.",
          file=sys.stderr)
    return False


def cmd_setup(args) -> int:
    """Pull the models and fetch the index, so first run needs nothing else."""
    import tarfile
    import tempfile

    import httpx

    from .app import INDEX_URL

    if not ensure_ollama(args.ollama, args.install_ollama):
        return 1
    print(f"ollama    {args.ollama}")
    tags = httpx.get(f"{args.ollama.rstrip('/')}/api/tags", timeout=10.0).json()
    present = {m["name"] for m in tags.get("models", [])}

    llm = args.llm_model
    if not llm:
        llm, why = default_llm()
        print(f"answering model  {why}")
    for model in (args.embed_model, llm):
        if model in present:
            print(f"  ok   {model}")
            continue
        low = model.lower()
        size = (" (~5.7 GB)" if "9b" in low else " (~3.4 GB)" if "4b" in low
                else " (~0.6 GB)")
        print(f"  pulling {model}{size} — first run only")
        with httpx.stream("POST", f"{args.ollama.rstrip('/')}/api/pull",
                          json={"model": model}, timeout=None) as r:
            last = ""
            for line in r.iter_lines():
                if not line:
                    continue
                status = orjson.loads(line).get("status", "")
                if status != last:
                    print(f"    {status}")
                    last = status

    index = pathlib.Path(args.index)
    print(f"index     {index}")
    if (index / "manifest.json").exists():
        print("  ok   already present")
    else:
        print("  downloading (~270 MB)")
        index.parent.mkdir(parents=True, exist_ok=True)
        # The release lives on a private repository, so an anonymous GET returns
        # 404 rather than 403. Try a token if one is around, then fall back to the
        # gh CLI, which already holds the user's credentials.
        headers = {}
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
                with httpx.stream("GET", INDEX_URL, follow_redirects=True, timeout=None,
                                  headers=headers) as r:
                    r.raise_for_status()
                    total = int(r.headers.get("content-length") or 0)
                    done = 0
                    for chunk in r.iter_bytes(1 << 20):
                        tmp.write(chunk)
                        done += len(chunk)
                        if total:
                            print(f"\r    {done / 1e6:5.0f} / {total / 1e6:.0f} MB", end="")
                path = tmp.name
            print()
        except httpx.HTTPStatusError as exc:
            if path:
                pathlib.Path(path).unlink(missing_ok=True)
                path = None
            if exc.response.status_code not in (401, 403, 404):
                raise
            print("\n  direct download failed; trying the gh CLI")
            if not shutil.which("gh"):
                print("\n  This release is on a private repository, so it cannot be "
                      "fetched anonymously.\n"
                      "  Either install the GitHub CLI (`gh auth login`), or set "
                      "GITHUB_TOKEN,\n"
                      "  or copy dist/kobold-index from a machine that has it and pass "
                      "--index.", file=sys.stderr)
                return 1
            target = pathlib.Path(tempfile.gettempdir()) / "kobold-index.tar.gz"
            target.unlink(missing_ok=True)
            # The tag is whatever INDEX_URL points at, so a release bump cannot
            # leave this fallback fetching the previous index.
            tag = INDEX_URL.split("/releases/download/")[1].split("/")[0]
            code = subprocess.call(["gh", "release", "download", tag,
                                    "--repo", "DeastinY/kleverkobold",
                                    "--pattern", "kobold-index.tar.gz",
                                    "--output", str(target)])
            if code != 0 or not target.exists():
                print("  gh could not fetch it either.", file=sys.stderr)
                return 1
            path = str(target)
        with tarfile.open(path) as tar:
            tar.extractall(index.parent, filter="data")
        pathlib.Path(path).unlink(missing_ok=True)
        print("  ok   unpacked")

    print("\nready:  kobold serve")
    return 0


def cmd_serve(args) -> int:
    from .server import serve
    model, auto = _llm(args)
    serve(args.index, args.ollama, args.host, args.port, args.backend,
          model, getattr(args, "embed_override", None),
          context_chars=getattr(args, "context_chars", None), auto_model=auto,
          report_url=getattr(args, "report_url", None),
          update_check=not (args.no_update_check or os.environ.get("KOBOLD_NO_UPDATE_CHECK")))
    return 0


def cmd_upgrade(args) -> int:
    """Say what is installed and what is out; fetch the newer one unless told only to look."""
    from . import update
    seen = update.check()
    current = seen["current"] or "unknown"
    if not seen["checked"]:
        print(f"installed {current}; could not reach GitHub to see what is newer.")
    elif not seen["behind"]:
        print(f"installed {current}; that is the newest ({seen['date']}). Nothing to do.")
        if not args.force:
            return 0
    else:
        print(f"installed {current}; newest is {seen['latest']} ({seen['date']}): {seen['message']}")
    if args.check:
        return 1 if seen["behind"] else 0
    if not seen["tool"]:
        print("This kobold runs from a checkout: update it with `git pull`.")
        return 1
    print(f"running {seen['command']}", flush=True)
    ok, out = update.upgrade()
    print(out)
    if ok:
        print("Upgraded. Restart `kobold serve` to run the new one.")
    return 0 if ok else 1


def cmd_mcp(args) -> int:
    from .mcp_server import serve
    model, _ = _llm(args)
    serve(args.index, args.ollama, llm_model=model)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="kobold", description="Pathfinder 2e rules assistant")
    ap.add_argument("--index", type=pathlib.Path, default=DEFAULT_INDEX)
    ap.add_argument("--ollama", default=DEFAULT_OLLAMA,
                    help="model server URL; with --backend openai this is its base URL")
    ap.add_argument("--backend", choices=("ollama", "openai"), default="ollama",
                    help="'openai' points at any OpenAI-compatible server "
                         "(mlx-serve, vllm-mlx, LM Studio, llama.cpp)")
    ap.add_argument("--llm-model", dest="llm_override",
                    help="the answering model. Default qwen3.5:4b (93/109 on the holdout, "
                         "half the memory and twice the speed of qwen3.5:9b, which scores "
                         "100/109 and is the 'Better' preset in the web UI). Below 4b it "
                         "starts answering PF2e questions with D&D 5e rules -- see "
                         "notes/experiments.md.")
    ap.add_argument("--embed-model", dest="embed_override",
                    help="override the embedding model — must be the one the index "
                         "was built with, and is checked at startup")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ask", help="answer a rules question with citations")
    p.add_argument("question")
    p.add_argument("-k", type=int, default=DEFAULT_K)
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-rerank", action="store_true",
                   help="skip the listwise rerank; slightly faster, worse on hard questions")
    p.add_argument("--timings", action="store_true",
                   help="print seconds spent per stage to stderr")
    p.add_argument("--scope", choices=SCOPES, default=DEFAULT_SCOPE, help=SCOPE_HELP)
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("chat", help="a conversation: each question may follow up on the last")
    p.add_argument("-k", type=int, default=DEFAULT_K)
    p.add_argument("--no-rerank", action="store_true")
    p.add_argument("--timings", action="store_true",
                   help="print seconds spent per stage to stderr, condense included")
    p.set_defaults(func=cmd_chat)

    p = sub.add_parser("search", help="show what retrieval finds, without answering")
    p.add_argument("question")
    p.add_argument("-k", type=int, default=DEFAULT_K)
    p.add_argument("--no-rerank", action="store_true")
    p.add_argument("--scope", choices=SCOPES, default=DEFAULT_SCOPE, help=SCOPE_HELP)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("setup", help="pull the models and fetch the index")
    p.add_argument("--llm-model", default=None,
                   help="answering model to pull (default qwen3.5:4b; qwen3.5:9b is the "
                        "web UI's 'Better' preset and is pulled on first use)")
    p.add_argument("--embed-model", default="qwen3-embedding:0.6b")
    p.add_argument("--install-ollama", action="store_true",
                   help="install Ollama too (brew on macOS, the official script on Linux)")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("doctor", help="check Ollama, models and index")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("serve", help="web UI for looking things up at the table")
    p.set_defaults(func=cmd_serve)
    p.add_argument("--host", default="127.0.0.1",
                   help="0.0.0.0 to let other devices on your network reach it")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--report-url", default=None,
                   help="where the page's 'Report a wrong answer' form posts (see "
                        "deploy/report-worker); or KOBOLD_REPORT_URL. Defaults to this "
                        "project's mailbox; pass '' to disable and fall back to a GitHub issue.")
    p.add_argument("--context-chars", type=int, default=None,
                   help="characters of each entry shown to the model (default 1600). "
                        "1000 scored the same on the holdout and cuts prompt-processing "
                        "time on a laptop, at the cost of truncating longer entries.")
    p.add_argument("--no-update-check", action="store_true",
                   help="do not ask GitHub whether a newer kobold is out (or set "
                        "KOBOLD_NO_UPDATE_CHECK). The check sends nothing but the request.")

    p = sub.add_parser("upgrade", help="fetch the newest kobold, if there is one")
    p.set_defaults(func=cmd_upgrade)
    p.add_argument("--check", action="store_true",
                   help="only say whether one is out; exit 1 if so")
    p.add_argument("--force", action="store_true", help="run the upgrade even when up to date")

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
