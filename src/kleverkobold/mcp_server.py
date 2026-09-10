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

from .app import DEFAULT_K, Assistant, OllamaError

PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "kobold_ask",
        "description": (
            "Answer a Pathfinder 2e rules question using the Archives of Nethys, "
            "with source URLs. Handles natural phrasing: describe a feat instead of "
            "naming it, ask what to do in a situation, or use pre-Remaster terms."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The rules question."},
                "k": {"type": "integer", "description": "Excerpts to retrieve (default 8)."},
            },
            "required": ["question"],
        },
    },
    {
        "name": "kobold_search",
        "description": (
            "Retrieve Pathfinder 2e rules excerpts without answering. Returns the "
            "matching Archives of Nethys entries with their text and URLs, for the "
            "caller to reason over itself."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "k": {"type": "integer", "description": "Excerpts to retrieve (default 8)."},
            },
            "required": ["question"],
        },
    },
]


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
            if not question:
                return _result("A question is required.", True)
            try:
                a = get()
                if name == "kobold_ask":
                    out = a.ask(question, k=int(args.get("k") or DEFAULT_K))
                    lines = [out["answer"], "", "Sources:"]
                    lines += [f"- {s['name']} ({s['category']}) {s['url']}" for s in out["sources"]]
                    return _result("\n".join(lines))
                if name == "kobold_search":
                    hits = a.search(question, k=int(args.get("k") or DEFAULT_K))
                    blocks = [f"## {h.name} ({h.category})\n{h.url}\n\n{h.text[:1600]}"
                              for h in hits]
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
