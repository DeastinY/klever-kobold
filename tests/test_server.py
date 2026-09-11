"""The HTTP layer: request parsing, the client pool, and the routes over a live socket."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
from conftest import plan_reply

from kleverkobold import server as s
from kleverkobold import update
from kleverkobold.app import HISTORY_CHARS, OllamaError


def test_clamp():
    assert s._clamp("5", 1, 10, 3) == 5
    assert s._clamp("50", 1, 10, 3) == 10
    assert s._clamp("-1", 1, 10, 3) == 1
    assert s._clamp("x", 1, 10, 3) == 3
    assert s._clamp(None, 1, 10, 3) == 3


BASE = s.Config(backend="ollama", base_url="http://localhost:11434", llm_model="qwen3.5:4b",
                context_chars=1600, remote_embedder=False, key_digest="")


def test_read_config_defaults_and_overrides():
    assert s._read_config({}, BASE, "") == BASE
    cfg = s._read_config({"backend": ["openai"], "base": ["http://lm:1234/v1/"],
                          "model": ["gpt"], "ctx": ["999999"], "embed": ["backend"]}, BASE, "k")
    assert cfg.backend == "openai" and cfg.base_url == "http://lm:1234"
    assert cfg.llm_model == "gpt" and cfg.context_chars == 8000
    assert cfg.remote_embedder is True and cfg.key_digest == s._key_digest("k")
    assert cfg.key_digest != "k" and len(cfg.key_digest) == 64


def test_read_config_rejects_bad_backends_and_urls():
    cfg = s._read_config({"backend": ["carrier-pigeon"], "base": ["file:///etc/passwd"],
                          "ctx": ["abc"]}, BASE, "")
    assert cfg.backend == "ollama" and cfg.base_url == BASE.base_url
    assert cfg.context_chars == 1600
    assert s._read_config({"base": ["http://" + "x" * 500]}, BASE, "").base_url == BASE.base_url
    assert s._read_config({"model": ["m" * 300]}, BASE, "").llm_model == "m" * 200


def test_read_history_caps_lengths():
    turns = s._read_history({"followup": ["1"], "prev_q": ["q" * 500], "prev_a": ["a" * 2000],
                             "prev_std": ["s" * 500]})
    assert len(turns) == 1
    assert len(turns[0].question) == 400 and len(turns[0].answer) == HISTORY_CHARS
    assert len(turns[0].standalone) == 400


def test_has_model():
    assert s._has_model(["qwen3.5:4b", "x:latest"], "qwen3.5:4b")
    assert s._has_model(["x:latest"], "x")
    assert s._has_model(["x"], "x:latest")
    assert not s._has_model(["x"], "y")
    assert not s._has_model(["x"], "")


def test_report_url(monkeypatch):
    assert s._report_url("http://mine") == "http://mine"
    assert s._report_url("") == ""
    monkeypatch.delenv("KOBOLD_REPORT_URL", raising=False)
    assert s._report_url(None) == s.DEFAULT_REPORT_URL
    monkeypatch.setenv("KOBOLD_REPORT_URL", "http://env")
    assert s._report_url(None) == "http://env"


def test_hits_serialise_and_trim(assistant):
    hit = assistant._hit(0)
    hit.text = "x" * 20000
    row = s._hits([hit])[0]
    assert row["name"] == "Treat Wounds" and row["category"] == "action"
    assert len(row["text"]) == 9000 and row["corpus"] == "aon"
    assert row["traits"] == [] and row["legacy_name"] == []


def test_random_entries_are_current_and_short(assistant):
    rows = s._random_entries(assistant, n=4)
    assert 0 < len(rows) <= 4
    assert all(set(r) == {"name", "category", "level"} for r in rows)
    assert "Magic Missile" not in {r["name"] for r in rows}


class Base:
    """The smallest thing a Pool needs: something with `variant`."""

    def __init__(self):
        self.made = []

    def variant(self, **kw):
        v = Variant(kw)
        self.made.append(v)
        return v


class Variant:
    def __init__(self, kw):
        self.kw, self.closed, self.required = kw, False, 0

    def require_embedder(self):
        self.required += 1

    def close(self):
        self.closed = True


def test_pool_returns_base_and_bounds_variants():
    base = Base()
    pool = s.Pool(base, BASE)
    assert pool.get(BASE, "") is base
    cfgs = [s.Config("openai", f"http://h{i}", "m", 1600, False, "") for i in range(s.Pool.LIMIT + 2)]
    first = pool.get(cfgs[0], "key")
    assert first.kw["api_key"] == "key" and first.required == 1
    assert pool.get(cfgs[0], "key") is first and first.required == 2
    for cfg in cfgs[1:]:
        pool.get(cfg, "")
    assert first.closed is True                      # evicted, oldest first
    assert len(pool._variants) == s.Pool.LIMIT
    assert base.made[-1].closed is False


# --- the routes, over a real socket ------------------------------------------

@pytest.fixture
def live(assistant):
    config = s.Config(backend="ollama", base_url=assistant.base_url,
                      llm_model="fake-llm", context_chars=assistant.context_chars,
                      remote_embedder=False, key_digest="")
    health = {"state": "ready", "detail": "awake", "defaults": {"lore": True}}
    httpd = ThreadingHTTPServer(("127.0.0.1", 0),
                                s.make_handler(s.Pool(assistant, config), threading.Lock(), health))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}", health
    finally:
        httpd.shutdown()
        httpd.server_close()


def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get("Content-Type", "")


def sse(body: bytes) -> list[dict]:
    return [json.loads(line[6:]) for line in body.decode().split("\n") if line.startswith("data: ")]


def test_page_health_examples_and_404(live):
    url, _ = live
    status, body, ctype = get(url + "/")
    assert status == 200 and ctype.startswith("text/html") and b"<" in body
    assert get(url + "/index.html")[0] == 200
    status, body, _ = get(url + "/api/health")
    assert status == 200 and json.loads(body)["state"] == "ready"
    status, body, _ = get(url + "/api/examples")
    assert status == 200 and json.loads(body)["entries"]
    assert get(url + "/nope")[0] == 404


def test_search_route(live, client):
    url, _ = live
    assert get(url + "/api/search")[0] == 400
    client.replies = [plan_reply("treat wounds", "action")]
    status, body, _ = get(url + "/api/search?q=How+does+Treat+Wounds+work&k=2&rerank=0")
    assert status == 200
    payload = json.loads(body)
    assert payload["scope"] == "rules" and payload["hits"][0]["name"] == "Treat Wounds"
    assert "standalone" not in payload


def test_search_route_with_followup_and_lore(live, client):
    url, _ = live
    client.replies = ["Who rules Cheliax?", plan_reply("cheliax ruler", "", "lore")]
    status, body, _ = get(url + "/api/search?q=and+who+rules+it&k=3&rerank=0&scope=auto"
                          "&followup=1&prev_q=Tell+me+about+Cheliax")
    payload = json.loads(body)
    assert status == 200 and payload["standalone"] == "Who rules Cheliax?"
    assert payload["scope"] == "lore"
    assert any(h["corpus"] == "pathfinderwiki" for h in payload["hits"])


def test_search_route_reports_backend_errors(live, client):
    url, _ = live

    def down(*a, **k):
        raise OllamaError("Cannot reach Ollama.")

    client.chat = down
    status, body, _ = get(url + "/api/search?q=x&rerank=0")
    assert status == 503 and "Cannot reach" in json.loads(body)["error"]

    def broken(*a, **k):
        raise RuntimeError("kaput")

    client.chat = lambda *a, **k: ""
    client.embed = broken    # the rewrite absorbs a chat failure; embedding cannot be skipped
    status, body, _ = get(url + "/api/search?q=x&rerank=0")
    assert status == 500 and "RuntimeError: kaput" in json.loads(body)["error"]


def test_search_route_waits_for_warmup(live):
    url, health = live
    health["state"] = "loading"
    health["detail"] = "loading the language model…"
    status, body, _ = get(url + "/api/search?q=x")
    assert status == 503 and "loading" in json.loads(body)["error"]
    # A configuration that embeds elsewhere is not waiting on this server: it gets
    # through to its own backend, which here is unreachable, and says so instead.
    status, body, _ = get(url + "/api/search?q=x&embed=backend&backend=openai&base=http://127.0.0.1:9")
    assert status == 503 and "loading" not in json.loads(body)["error"]


def test_ask_route_streams_events(live, client):
    url, _ = live
    client.replies = [plan_reply("prone", "condition")]
    status, body, ctype = get(url + "/api/ask?q=what+does+prone+do&k=2&rerank=0")
    assert status == 200 and ctype.startswith("text/event-stream")
    events = sse(body)
    kinds = [e["event"] for e in events]
    assert kinds[0] == "sources" and kinds[-1] == "done" and "token" in kinds
    assert events[0]["hits"][-1]["name"] == "Prone" and events[0]["scope"] == "rules"
    assert "hits" in events[0] and "plan" not in events[0]
    assert events[-1]["answer"] == "The kobold says: ten minutes."
    assert isinstance(events[-1]["mentions"], list)


def test_ask_route_error_event(live, client):
    url, _ = live

    def down(*a, **k):
        raise OllamaError("Cannot reach Ollama.")

    client.chat = down
    events = sse(get(url + "/api/ask?q=x")[1])
    assert events == [{"event": "error", "error": "Cannot reach Ollama."}]


def test_pull_route_only_knows_the_two_models(live):
    url, _ = live
    assert get(url + "/api/pull?model=llama-anything")[0] == 400


def test_test_route_reports_unreachable_backend(live):
    url, _ = live
    status, body, _ = get(url + "/api/test?backend=openai&base=http://127.0.0.1:9&model=m",
                          headers={s.KEY_HEADER: "secret"})
    payload = json.loads(body)
    assert status == 200 and payload["ok"] is False and payload["models"] == []
    assert "secret" not in body.decode()
    assert payload["backend"] == "openai" and payload["base_url"] == "http://127.0.0.1:9"


def post(url, body=None):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_upgrade_routes(live, monkeypatch, tmp_path):
    url, health = live
    monkeypatch.setattr(update, "config_path", lambda: tmp_path / "config.json")
    assert post(url + "/api/nothing")[0] == 404
    status, body = post(url + "/api/auto-upgrade", {"on": True})
    assert status == 200 and body == {"auto_upgrade": True}
    assert update.auto_upgrade() is True and health["defaults"]["auto_upgrade"] is True
    assert post(url + "/api/auto-upgrade", {"on": False})[1] == {"auto_upgrade": False}

    monkeypatch.setattr(update, "upgrade", lambda: (False, "uv: not found"))
    status, body = post(url + "/api/upgrade")
    assert status == 500 and body["ok"] is False and "not found" in body["output"]

    restarted = []
    monkeypatch.setattr(update, "upgrade", lambda: (True, "Updated kleverkobold"))
    monkeypatch.setattr(update, "restart", lambda: restarted.append(1))
    status, body = post(url + "/api/upgrade")
    assert status == 200 and body["ok"] and body["restarting"]
    import time
    time.sleep(0.8)
    assert restarted == [1]


def test_upgrade_refused_off_the_loopback(live, monkeypatch):
    url, _ = live
    monkeypatch.setattr(s.BaseHTTPRequestHandler, "client_address", ("10.0.0.7", 1), raising=False)
    # The handler reads client_address from the instance; force the check itself.
    handler = None
    for cls in s.BaseHTTPRequestHandler.__subclasses__():
        if cls.__name__ == "Handler":
            handler = cls
    assert handler is not None
    monkeypatch.setattr(handler, "_local", lambda self: False)
    assert post(url + "/api/upgrade")[0] == 403
    assert post(url + "/api/auto-upgrade", {"on": True})[0] == 403


def test_open_browser_respects_the_switches(monkeypatch):
    import webbrowser
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url, new=0: opened.append(url) or True)
    monkeypatch.delenv("KOBOLD_NO_BROWSER", raising=False)
    monkeypatch.delenv(update.JUST_UPGRADED, raising=False)
    assert s.open_browser("http://localhost:1", wanted=False) is False
    monkeypatch.setenv("KOBOLD_NO_BROWSER", "1")
    assert s.open_browser("http://localhost:1") is False
    monkeypatch.delenv("KOBOLD_NO_BROWSER")
    monkeypatch.setenv(update.JUST_UPGRADED, "1")
    assert s.open_browser("http://localhost:1") is False     # the page is already open
    monkeypatch.delenv(update.JUST_UPGRADED)
    assert s.open_browser("http://localhost:1") is True and opened == ["http://localhost:1"]

    def no_browser(url, new=0):
        raise webbrowser.Error("no browser")

    monkeypatch.setattr(webbrowser, "open", no_browser)
    assert s.open_browser("http://localhost:1") is False


def test_serve_has_a_no_browser_flag():
    from kleverkobold import __main__ as cli
    with pytest.raises(SystemExit) as exc:
        cli.main(["serve", "--no-browser", "--help"])
    assert exc.value.code == 0
