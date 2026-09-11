"""MCP server over stdio, so the assistant drops into Claude Desktop or Claude Code.

Two tools, deliberately separate:

``kobold_ask``     the full pipeline -- rewrite, retrieve, answer with citations.
``kobold_search``  retrieval only, returning the excerpts. Useful when the caller is
                 itself a capable model: it can read the rules text and reason
                 about it directly, which measured better than any local model
                 answering on its own.

Implemented against the raw protocol rather than an SDK, because the whole point
of this package is that it installs with four pure-Python dependencies.
"""

from __future__ import annotations

import pathlib
import sys

import orjson

from .app import DEFAULT_K, DEFAULT_SCOPE, SCOPES, Assistant, OllamaError

PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "kobold_ask",
        "description": (
            "Answer a Pathfinder 2e question using the Archives of Nethys (rules) and "
            "PathfinderWiki (Golarion setting lore), with source URLs. Handles natural "
            "phrasing: describe a feat instead of naming it, ask what to do in a situation, "
            "use pre-Remaster terms, or ask who rules Cheliax."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The question."},
                "k": {"type": "integer", "description": "Excerpts to retrieve (default 8)."},
                "scope": {"type": "string", "enum": list(SCOPES),
                          "description": "rules: Archives of Nethys only. lore: rules and "
                                         "PathfinderWiki. auto (default): decided per question; "
                                         "a rules question never sees lore."},
            },
            "required": ["question"],
        },
    },
    {
        "name": "kobold_search",
        "description": (
            "Retrieve Pathfinder 2e excerpts without answering: rules entries from the "
            "Archives of Nethys and, for setting questions, lore from PathfinderWiki, "
            "each with its text and URL, for the caller to reason over itself."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string",
                             "description": "What to search for. May be empty when kinds, level "
                                            "or traits are given: then the matching entries are "
                                            "listed, by level and name, with no model involved."},
                "k": {"type": "integer", "description": "Excerpts to retrieve (default 8)."},
                "scope": {"type": "string", "enum": list(SCOPES),
                          "description": "rules, lore, or auto (default)."},
                "kinds": {"type": "array", "items": {"type": "string"},
                          "description": "Entry kinds to allow: feat, spell, action, condition, "
                                         "equipment, weapon, armor, creature, hazard, trait, "
                                         "rules, class-feature, ritual, archetype, background, "
                                         "heritage, deity, shield."},
                "level": {"type": "string",
                          "description": "A level or range: '4', '1-4', '10-' (10 and up), "
                                         "'..2' (up to 2). '-1' is the level minus one."},
                "traits": {"type": "array", "items": {"type": "string"},
                           "description": "Traits the entry must carry, e.g. ['flourish']."},
            },
        },
    },
]


def _filters(args: dict) -> dict | None:
    """The tool's kinds/level/traits as the Assistant's filters, or None."""
    from .server import _read_filters
    query = {}
    if args.get("kinds"):
        query["kind"] = [",".join(str(k) for k in args["kinds"])]
    if args.get("level"):
        query["lvl"] = [str(args["level"])]
    if args.get("traits"):
        query["traits"] = [",".join(str(t) for t in args["traits"])]
    return _read_filters(query)


def _result(text: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def serve(index_dir: pathlib.Path, ollama_url: str, llm_model: str | None = None) -> None:
    assistant: Assistant | None = None

    def get() -> Assistant:
        nonlocal assistant
        if assistant is None:
            assistant = Assistant(index_dir, ollama_url, llm_model=llm_model)
        return assistant

    def handle(request: dict) -> dict | None:
        method = request.get("method")
        if method == "initialize":
            return {"protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "kleverkobold", "version": "0.1.0"}}
        if method == "tools/list":
            return {"tools": TOOLS}
        if method == "tools/call":
            params = request.get("params") or {}
            name = params.get("name")
            args = params.get("arguments") or {}
            question = (args.get("question") or "").strip()
            filters = _filters(args) if name == "kobold_search" else None
            if not question and not filters:
                return _result("A question is required.", True)
            scope = args.get("scope") or DEFAULT_SCOPE
            if scope not in SCOPES:
                return _result(f"scope must be one of {', '.join(SCOPES)}.", True)
            try:
                a = get()
                if name == "kobold_search" and not question:
                    hits = a.browse(filters, scope=scope, limit=int(args.get("k") or 24))
                    lines = [f"- {h.name} ({h.category}"
                             f"{', level ' + str(h.level) if h.level is not None else ''}) "
                             f"{h.url}" for h in hits]
                    return _result("\n".join(lines) or "Nothing matched.")
                if name == "kobold_ask":
                    out = a.ask(question, k=int(args.get("k") or DEFAULT_K), scope=scope)
                    lines = [out["answer"], "", "Sources:"]
                    lines += [f"- {s['name']} ({s['category']}"
                              f"{', lore' if s.get('corpus') == 'pathfinderwiki' else ''}) "
                              f"{s['url']}" for s in out["sources"]]
                    return _result("\n".join(lines))
                if name == "kobold_search":
                    hits = a.search(question, k=int(args.get("k") or DEFAULT_K), scope=scope,
                                    filters=filters)
                    blocks = [f"## {h.name} ({h.category}{', Golarion lore' if h.lore else ''})"
                              f"\n{h.url}\n\n{h.text[:1600]}" for h in hits]
                    return _result("\n\n---\n\n".join(blocks) or "Nothing matched.")
                return _result(f"Unknown tool {name!r}.", True)
            except OllamaError as exc:
                return _result(str(exc), True)
            except Exception as exc:  # keep the transport alive on any tool failure
                return _result(f"{type(exc).__name__}: {exc}", True)
        return None

    for line in sys.stdin.buffer:
        line = line.strip()
        if not line:
            continue
        try:
            request = orjson.loads(line)
        except orjson.JSONDecodeError:
            continue
        result = handle(request)
        if request.get("id") is None:  # notification; nothing to answer
            continue
        response = {"jsonrpc": "2.0", "id": request["id"]}
        if result is None:
            response["error"] = {"code": -32601, "message": f"unknown method {request.get('method')!r}"}
        else:
            response["result"] = result
        sys.stdout.buffer.write(orjson.dumps(response) + b"\n")
        sys.stdout.buffer.flush()
