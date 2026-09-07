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

import html
import json
import pathlib
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .app import DEFAULT_INDEX, DEFAULT_OLLAMA, Assistant, OllamaError

PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PF2e Rules</title>
<style>
:root{--bg:#f4f2f1;--card:#fff;--ink:#191517;--soft:#4a4341;--muted:#756c69;
--line:#d9d1ce;--accent:#8a1b2e;--warn:#8a5a12}
@media(prefers-color-scheme:dark){:root{--bg:#131011;--card:#1b1718;--ink:#ece7e5;
--soft:#c6bebb;--muted:#968c89;--line:#332d2e;--accent:#dd6d7d;--warn:#d3a04a}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 ui-sans-serif,system-ui,sans-serif}
.wrap{max-width:56rem;margin:0 auto;padding:1.25rem 1rem 4rem}
h1{font-size:1.05rem;margin:0 0 .75rem;letter-spacing:.02em;font-weight:600}
h1 small{color:var(--muted);font-weight:400}
form{display:flex;gap:.5rem;position:sticky;top:0;background:var(--bg);padding:.5rem 0 .75rem;z-index:2}
input{flex:1;padding:.7rem .85rem;font-size:1rem;border:1px solid var(--line);
background:var(--card);color:var(--ink);border-radius:6px}
input:focus{outline:2px solid var(--accent);outline-offset:1px}
button{padding:.7rem 1rem;font-size:.92rem;border:1px solid var(--line);background:var(--card);
color:var(--ink);border-radius:6px;cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
button[disabled]{opacity:.5;cursor:default}
.hint{color:var(--muted);font-size:.82rem;margin:0 0 .5rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;
padding:.8rem .95rem;margin:.6rem 0}
.card h2{font-size:.98rem;margin:0 0 .15rem}
.card h2 a{color:var(--ink);text-decoration:none}
.card h2 a:hover{text-decoration:underline}
.meta{color:var(--muted);font-size:.78rem;margin-bottom:.5rem}
.body{white-space:pre-wrap;font-size:.9rem;color:var(--soft);max-height:15rem;overflow:auto}
.answer{border-left:3px solid var(--warn)}
.answer .flag{color:var(--warn);font-size:.78rem;margin-bottom:.4rem}
.answer .body{color:var(--ink);max-height:none}
.spin{color:var(--muted);font-size:.85rem;padding:.5rem 0}
.err{color:var(--accent)}
</style></head><body><div class="wrap">
<h1>Pathfinder 2e rules <small>— Archives of Nethys, offline</small></h1>
<form id="f"><input id="q" placeholder="describe it, name it, or ask what happens…" autofocus
 autocomplete="off"><button class="primary">Look up</button>
<button id="askbtn" type="button">Ask</button></form>
<p class="hint">Look up shows the rules entries themselves. <b>Ask</b> writes an answer from them —
good for straight lookups, unreliable for rule interactions. Check the citation.</p>
<div id="out"></div>
</div><script>
const out=document.getElementById('out'),q=document.getElementById('q');
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function busy(m){out.innerHTML='<p class="spin">'+m+'</p>'}
function cards(hits){return hits.map(h=>`<div class="card"><h2><a href="${h.url}"
 target="_blank" rel="noreferrer">${esc(h.name)}</a></h2><div class="meta">${esc(h.category)}${
 h.level!==null&&h.level!==undefined?' · level '+h.level:''}${h.traits&&h.traits.length?' · '+
 esc(h.traits.join(', ')):''}</div><div class="body">${esc(h.text)}</div></div>`).join('')}
async function go(mode){
  const text=q.value.trim(); if(!text)return;
  busy(mode==='ask'?'reading the rules…':'searching…');
  try{
    const r=await fetch('/api/'+mode+'?q='+encodeURIComponent(text));
    const d=await r.json();
    if(d.error){out.innerHTML='<p class="err">'+esc(d.error)+'</p>';return}
    let h='';
    if(d.answer){h+=`<div class="card answer"><div class="flag">Generated from the entries below —
      verify against the citations, especially for rule interactions.</div>
      <div class="body">${esc(d.answer)}</div></div>`}
    h+=cards(d.hits||[]);
    out.innerHTML=h||'<p class="spin">Nothing matched.</p>';
  }catch(e){out.innerHTML='<p class="err">'+esc(String(e))+'</p>'}
}
document.getElementById('f').addEventListener('submit',e=>{e.preventDefault();go('search')});
document.getElementById('askbtn').addEventListener('click',()=>go('ask'));
document.addEventListener('keydown',e=>{if(e.key==='/'&&document.activeElement!==q){
  e.preventDefault();q.focus();q.select()}});
</script></body></html>"""


def make_handler(assistant: Assistant, lock: threading.Lock):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args) -> None:  # quiet by default
            pass

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
            if parsed.path not in ("/api/search", "/api/ask"):
                self._send(404, b'{"error":"not found"}', "application/json")
                return

            question = (urllib.parse.parse_qs(parsed.query).get("q") or [""])[0].strip()
            if not question:
                self._send(400, b'{"error":"a question is required"}', "application/json")
                return
            try:
                # One model, one card: serialise so two players hitting enter at
                # the same time queue instead of thrashing Ollama.
                with lock:
                    if parsed.path == "/api/ask":
                        result = assistant.ask(question)
                        hits = assistant.search(question, plan=result["plan"])
                        payload = {"answer": result["answer"], "hits": _hits(hits)}
                    else:
                        payload = {"hits": _hits(assistant.search(question))}
            except OllamaError as exc:
                self._send(503, json.dumps({"error": str(exc)}).encode(), "application/json")
                return
            except Exception as exc:  # keep the tab alive; show what broke
                self._send(500, json.dumps({"error": f"{type(exc).__name__}: {exc}"}).encode(),
                           "application/json")
                return
            self._send(200, json.dumps(payload).encode(), "application/json; charset=utf-8")

    return Handler


def _hits(hits) -> list[dict]:
    return [{"name": h.name, "category": h.category.replace("-", " "), "level": h.level,
             "url": h.url, "text": h.text[:2200],
             "traits": []} for h in hits]


def serve(index_dir: pathlib.Path = DEFAULT_INDEX, ollama_url: str = DEFAULT_OLLAMA,
          host: str = "127.0.0.1", port: int = 8765) -> None:
    assistant = Assistant(index_dir, ollama_url)
    server = ThreadingHTTPServer((host, port), make_handler(assistant, threading.Lock()))
    shown = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    print(f"PF2e rules on http://{shown}:{port}  (ctrl-c to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
