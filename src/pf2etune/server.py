"""A small web UI for looking things up at the table.

Built on the standard library so the runtime keeps its four dependencies.

**The layout follows the evaluation, not the demo instinct.** Retrieved rules
excerpts are shown first and by default, because that is the part that measures
well: the entries come straight from Archives of Nethys and carry their own
links. The generated answer is opt-in, behind a button, and labelled — because
the same evaluation says it is reliable for lookups and unreliable for rule
interactions, which is exactly the question a table is most likely to ask.

Serving the answer first would look better and mislead more.
"""

from __future__ import annotations

import json
import pathlib
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .app import DEFAULT_INDEX, DEFAULT_OLLAMA, Assistant, OllamaError
from .ui import PAGE

def make_handler(assistant: Assistant, lock: threading.Lock, health: dict):
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
            if parsed.path not in ("/api/search", "/api/ask"):
                self._send(404, b'{"error":"not found"}', "application/json")
                return

            if health.get("state") != "ready":
                self._send(503, json.dumps({"error": health.get("detail", "still starting")})
                           .encode(), "application/json")
                return
            question = (urllib.parse.parse_qs(parsed.query).get("q") or [""])[0].strip()
            if not question:
                self._send(400, b'{"error":"a question is required"}', "application/json")
                return
            if parsed.path == "/api/ask":
                self._ask_stream(question)
                return
            try:
                # One model, one card: serialise so two players hitting enter at
                # the same time queue instead of thrashing Ollama.
                with lock:
                    payload = {"hits": _hits(assistant.search(question))}
            except OllamaError as exc:
                self._send(503, json.dumps({"error": str(exc)}).encode(), "application/json")
                return
            except Exception as exc:  # keep the tab alive; show what broke
                self._send(500, json.dumps({"error": f"{type(exc).__name__}: {exc}"}).encode(),
                           "application/json")
                return
            self._send(200, json.dumps(payload).encode(), "application/json; charset=utf-8")

        def _ask_stream(self, question: str) -> None:
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
                with lock:
                    for event in assistant.ask_stream(question):
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


def _hits(hits) -> list[dict]:
    return [{"name": h.name, "category": h.category.replace("-", " "), "level": h.level,
             "url": h.url, "text": h.text[:2200],
             "traits": []} for h in hits]


def serve(index_dir: pathlib.Path = DEFAULT_INDEX, ollama_url: str = DEFAULT_OLLAMA,
          host: str = "127.0.0.1", port: int = 8765, backend: str = "ollama",
          llm_model: str | None = None, embed_model: str | None = None,
          context_chars: int | None = None) -> None:
    assistant = Assistant(index_dir, ollama_url, backend=backend,
                          llm_model=llm_model, embed_model=embed_model,
                          **({"context_chars": context_chars} if context_chars else {}))
    health = {"state": "starting", "detail": "loading models…"}

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

    server = ThreadingHTTPServer((host, port), make_handler(assistant, threading.Lock(), health))
    shown = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    print(f"PF2e rules on http://{shown}:{port}  (ctrl-c to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
