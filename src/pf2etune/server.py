"""A small web UI for looking things up at the table.

Built on the standard library so the runtime keeps its four dependencies.

**Enter asks; the answer is labelled, and the entries are always underneath.**
The evaluation says the generated answer is reliable for lookups and unreliable
for rule interactions -- exactly the question a table is most likely to ask --
so the answer carries a standing caution and every claim links to the Archives
of Nethys entry it came from. Shift+Enter skips the answer and shows only the
entries. Questions and their answers are kept in the browser, so repeating one
is free.
"""

from __future__ import annotations

import collections
import hashlib
import json
import pathlib
import threading
import urllib.parse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .app import (DEFAULT_INDEX, DEFAULT_K, DEFAULT_OLLAMA, SMALL_LLM, Assistant, OllamaError,
                  probe_backend)
from .ui import PAGE

# The header the API key travels in. A header rather than a query parameter so it
# stays out of the URL, and therefore out of browser history, out of a Referer,
# and out of any access log anyone ever adds to this handler.
KEY_HEADER = "X-PF2E-Key"


@dataclass(frozen=True)
class Config:
    """The part of a request's settings that needs its own client.

    Hashable, because it is the key of the Assistant pool. ``key_digest`` rather
    than the key itself: the pool outlives the request, and a plaintext secret
    should not sit in a long-lived dict key where any traceback or repr of the
    pool would print it.
    """
    backend: str
    base_url: str
    llm_model: str
    context_chars: int
    remote_embedder: bool
    key_digest: str


class Pool:
    """One loaded index, several client configurations over it.

    The index is 250 MB of memory-mapped arrays and takes a second to load, so a
    settings change must not rebuild it: ``Assistant.variant`` shares all of it
    and only the HTTP client and model names differ. Keeping a handful of those
    alive means switching back and forth between two models is free, and the
    bound stops a page that sends a new model name per keystroke from opening
    unbounded connection pools.
    """

    LIMIT = 6

    def __init__(self, base: Assistant, base_config: Config) -> None:
        self.base = base
        self.base_config = base_config
        self._variants: collections.OrderedDict[Config, Assistant] = collections.OrderedDict()
        self._lock = threading.Lock()

    def get(self, config: Config, api_key: str) -> Assistant:
        if config == self.base_config:
            return self.base
        with self._lock:
            found = self._variants.get(config)
            if found is None:
                found = self.base.variant(
                    backend=config.backend, base_url=config.base_url,
                    llm_model=config.llm_model, api_key=api_key,
                    context_chars=config.context_chars,
                    remote_embedder=config.remote_embedder)
                self._variants[config] = found
                while len(self._variants) > self.LIMIT:
                    self._variants.popitem(last=False)[1].close()
            else:
                self._variants.move_to_end(config)
        # Outside the pool lock: on a remote embedder this is a model call, and
        # it must not block a second tab from reading its own settings.
        found.require_embedder()
        return found


def _clamp(raw: str | None, low: int, high: int, fallback: int) -> int:
    try:
        return max(low, min(high, int(raw)))
    except (TypeError, ValueError):
        return fallback


def _read_config(query: dict[str, list[str]], base: Config, api_key: str) -> Config:
    """Per-request settings, validated. Anything unset falls back to the server's own."""
    def one(name: str) -> str:
        return (query.get(name) or [""])[0].strip()

    asked = one("backend")
    backend = asked if asked in ("ollama", "openai") else base.backend
    base_url = one("base") or base.base_url
    # Only ever an HTTP endpoint: this runs a request on the user's behalf, and
    # file:// or a bare host is a mistake rather than a configuration.
    if not base_url.startswith(("http://", "https://")) or len(base_url) > 400:
        base_url = base.base_url
    # Normalised the same way the clients normalise it, so "…:11434/" and
    # "…/v1" are recognised as the server's own configuration rather than
    # opening a second, identical client for them.
    base_url = base_url.rstrip("/")
    if backend == "openai" and base_url.endswith("/v1"):
        base_url = base_url[:-3]
    model = one("model")[:200] or base.llm_model
    return Config(
        backend=backend, base_url=base_url, llm_model=model,
        # Sweeps put the useful range well inside these; the bounds exist so a
        # hand-edited URL cannot ask for a 2 MB prompt.
        context_chars=_clamp(one("ctx") or None, 200, 8000, base.context_chars),
        remote_embedder=one("embed") == "backend",
        key_digest=_key_digest(api_key))


def _key_digest(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest() if api_key else ""


def make_handler(pool: Pool, lock: threading.Lock, health: dict):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args) -> None:  # quiet by default
            pass

        def _sse(self, event: dict) -> None:
            self.wfile.write(b"data: " + json.dumps(event).encode() + b"\n\n")
            self.wfile.flush()

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path in ("/", "/index.html"):
                self._send(200, PAGE.encode(), "text/html; charset=utf-8")
                return
            if parsed.path == "/api/health":
                self._send(200, json.dumps(health).encode(), "application/json")
                return
            if parsed.path == "/api/examples":
                # A few random current entries, so the page can suggest questions
                # the corpus can actually answer. No model, no index scan beyond
                # a handful of random rows.
                self._send(200, json.dumps({"entries": _random_entries(pool.base)}).encode(),
                           "application/json; charset=utf-8")
                return
            if parsed.path not in ("/api/search", "/api/ask", "/api/test"):
                self._send(404, b'{"error":"not found"}', "application/json")
                return

            query = urllib.parse.parse_qs(parsed.query)
            # Read once, pass down, never store. The key exists only for the
            # lifetime of this request and the httpx client it configures.
            api_key = (self.headers.get(KEY_HEADER) or "").strip()
            config = _read_config(query, pool.base_config, api_key)

            if parsed.path == "/api/test":
                self._test(config, api_key)
                return

            # A configuration that does its own embedding does not depend on this
            # server's warmup at all, so it is allowed through while the local
            # models are still loading -- or when there are none. That is the
            # "add our retrieval to a model you already have" case.
            if health.get("state") != "ready" and not config.remote_embedder:
                self._send(503, json.dumps({"error": health.get("detail", "still starting")})
                           .encode(), "application/json")
                return
            question = (query.get("q") or [""])[0].strip()
            if not question:
                self._send(400, b'{"error":"a question is required"}', "application/json")
                return
            k = _clamp((query.get("k") or [None])[0], 1, 24, DEFAULT_K)
            rerank = (query.get("rerank") or ["1"])[0] != "0"
            max_tokens = _clamp((query.get("tokens") or [None])[0], 32, 4000,
                                pool.base.answer_tokens)
            if parsed.path == "/api/ask":
                self._ask_stream(question, config, api_key, k, rerank, max_tokens)
                return
            try:
                assistant = pool.get(config, api_key)
                # One model, one card: serialise so two players hitting enter at
                # the same time queue instead of thrashing Ollama.
                with lock:
                    payload = {"hits": _hits(assistant.search(question, k=k, rerank=rerank))}
            except OllamaError as exc:
                self._send(503, json.dumps({"error": str(exc)}).encode(), "application/json")
                return
            except Exception as exc:  # keep the tab alive; show what broke
                self._send(500, json.dumps({"error": f"{type(exc).__name__}: {exc}"}).encode(),
                           "application/json")
                return
            self._send(200, json.dumps(payload).encode(), "application/json; charset=utf-8")

        def _test(self, config: Config, api_key: str) -> None:
            """Reachability and model availability for a configuration.

            Nothing here echoes the key back, and the model list is the only
            thing the backend says that reaches the page.
            """
            embed_model = pool.base.manifest["ollama_embed"]
            body = {"backend": config.backend, "base_url": config.base_url,
                    "llm_model": config.llm_model, "embed_model": embed_model,
                    "remote_embedder": config.remote_embedder}
            try:
                models = probe_backend(config.backend, config.base_url, api_key)
            except OllamaError as exc:
                body.update(ok=False, models=[], error=str(exc))
                self._send(200, json.dumps(body).encode(), "application/json; charset=utf-8")
                return
            body.update(ok=True, models=models,
                        llm_ok=_has_model(models, config.llm_model),
                        embed_ok=_has_model(models, embed_model))
            self._send(200, json.dumps(body).encode(), "application/json; charset=utf-8")

        def _ask_stream(self, question: str, config: Config, api_key: str,
                        k: int, rerank: bool, max_tokens: int) -> None:
            """Answer over server-sent events.

            The answer is the slow half and it decodes a token at a time. Sending
            it as one JSON blob at the end means the page shows a spinner for the
            whole generation; streaming turns the same total into a first sentence
            after a few seconds.
            """
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            # No length is known up front, so the close is the terminator.
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                assistant = pool.get(config, api_key)
                with lock:
                    for event in assistant.ask_stream(question, k=k, rerank=rerank,
                                                      max_tokens=max_tokens):
                        if event["event"] == "sources":
                            event = {"event": "sources", "timings": event["timings"],
                                     "hits": _hits(event["hits"])}
                        self._sse(event)
            except OllamaError as exc:
                self._sse({"event": "error", "error": str(exc)})
            except (BrokenPipeError, ConnectionResetError):
                pass  # the tab went away mid-answer
            except Exception as exc:
                self._sse({"event": "error", "error": f"{type(exc).__name__}: {exc}"})

    return Handler


def _has_model(models: list[str], want: str) -> bool:
    """Is `want` in a backend's list, allowing for Ollama's implicit :latest tag?"""
    if not want:
        return False
    names = set(models)
    return (want in names or f"{want}:latest" in names
            or want.removesuffix(":latest") in names)


_EXAMPLE_KINDS = {"feat", "spell", "action", "condition", "equipment", "weapon", "creature"}


def _random_entries(assistant: Assistant, n: int = 8) -> list[dict]:
    import random
    meta = assistant.index.meta
    out, tries = [], 0
    while len(out) < n and tries < 200:
        tries += 1
        m = meta[random.randrange(len(meta))]
        if (m.get("category") in _EXAMPLE_KINDS and m.get("remaster_status") != "legacy"
                and m.get("name") and len(m["name"]) < 32 and m.get("summary")):
            out.append({"name": m["name"], "category": m["category"], "level": m.get("level")})
    return out


def _hits(hits) -> list[dict]:
    return [{"name": h.name, "category": h.category.replace("-", " "), "level": h.level,
             "url": h.url, "text": h.text[:9000], "summary": h.summary or "",
             "legacy_name": h.legacy_name, "traits": []} for h in hits]


def serve(index_dir: pathlib.Path = DEFAULT_INDEX, ollama_url: str = DEFAULT_OLLAMA,
          host: str = "127.0.0.1", port: int = 8765, backend: str = "ollama",
          llm_model: str | None = None, embed_model: str | None = None,
          context_chars: int | None = None, auto_model: bool = False) -> None:
    assistant = Assistant(index_dir, ollama_url, backend=backend,
                          llm_model=llm_model, embed_model=embed_model,
                          **({"context_chars": context_chars} if context_chars else {}))
    # The settings panel sends the server's own values back unchanged until
    # someone edits them, so describing the launch configuration as a Config lets
    # the pool recognise "no override" and hand back this Assistant.
    pool = Pool(assistant, Config(backend=backend, base_url=assistant.base_url,
                                  llm_model=assistant.manifest["ollama_llm"],
                                  context_chars=assistant.context_chars,
                                  remote_embedder=False, key_digest=""))
    # The settings panel seeds itself from this rather than hard-coding a copy of
    # the defaults, so `--llm-model` on the command line is what the panel shows.
    # Nothing here is secret: no key ever reaches the server's own configuration.
    health = {"state": "starting", "detail": "loading models…",
              "defaults": {"backend": backend, "base_url": assistant.base_url,
                           "llm_model": assistant.manifest["ollama_llm"],
                           "embed_model": assistant.manifest["ollama_embed"],
                           # The machine's 4B runs as the Faster preset, rerank off:
                           # measured the same with and without it, and it is one
                           # whole model call fewer on a laptop that is already busy.
                           "k": DEFAULT_K,
                           "rerank": not (auto_model and
                                          assistant.manifest["ollama_llm"] == SMALL_LLM),
                           "auto_model": auto_model,
                           "context_chars": assistant.context_chars,
                           "answer_tokens": assistant.answer_tokens},
              # Drives how loudly the panel warns about typing an API key into a
              # page with no authentication in front of it.
              "local_only": host in ("127.0.0.1", "localhost", "::1")}

    def warm() -> None:
        # In a thread so the page is servable immediately and can *say* what is
        # happening. Loading several gigabytes with a blank screen in front of it
        # is how this looked broken on a laptop.
        def progress(label: str, secs: float | None) -> None:
            if secs is None:
                health.update(state="loading", detail=f"loading the {label}…")
                print(f"  loading the {label}…", flush=True)
            else:
                print(f"  {label} ready in {secs:.1f}s", flush=True)

        try:
            timings = assistant.warmup(progress)
            health.update(state="ready",
                          detail=f"ready — models loaded in {sum(timings.values()):.1f}s")
            print("  ready", flush=True)
        except Exception as exc:
            health.update(state="error", detail=str(exc))
            print(f"  {exc}", flush=True)

    threading.Thread(target=warm, daemon=True).start()

    server = ThreadingHTTPServer((host, port), make_handler(pool, threading.Lock(), health))
    shown = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    print(f"PF2e rules on http://{shown}:{port}  (ctrl-c to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
