"""Everything that talks HTTP, against a transport that never opens a socket."""

import json

import httpx
import numpy as np
import orjson
import pytest

from kleverkobold import aon, wiki
from kleverkobold.app import Ollama, OllamaError, OpenAICompatible, client_for, probe_backend


def transport(handler):
    return httpx.MockTransport(handler)


# --- Archives of Nethys ---------------------------------------------------------

def test_aon_categories_and_count(monkeypatch):
    def handle(request):
        if request.url.path.endswith("/_count"):
            return httpx.Response(200, json={"count": 41743})
        body = json.loads(request.content)
        assert body["aggs"]["cats"]["terms"]["field"] == "category"
        return httpx.Response(200, json={"aggregations": {"cats": {"buckets": [
            {"key": "feat", "doc_count": 5000}, {"key": "spell", "doc_count": 1200}]}}})

    with httpx.Client(transport=transport(handle)) as client:
        assert aon.total_documents(client) == 41743
        cats = aon.categories(client)
    assert cats == [aon.Category("feat", 5000), aon.Category("spell", 1200)]


def test_aon_fetch_category_pages_until_short(monkeypatch):
    monkeypatch.setattr(aon, "PAGE_SIZE", 2)
    pages = {0: ["a", "b"], 2: ["c"]}

    def handle(request):
        body = json.loads(request.content)
        assert body["query"] == {"term": {"category": "feat"}} and body["size"] == 2
        hits = [{"_id": f"feat-{i}", "_source": {"name": i}} for i in pages.get(body["from"], [])]
        return httpx.Response(200, json={"hits": {"hits": hits}})

    with httpx.Client(transport=transport(handle)) as client:
        docs = list(aon.fetch_category(client, "feat"))
    assert [d["name"] for d in docs] == ["a", "b", "c"]
    assert docs[0]["_es_id"] == "feat-a"


def test_aon_fetch_category_stops_on_an_empty_page(monkeypatch):
    monkeypatch.setattr(aon, "PAGE_SIZE", 1)
    calls = []

    def handle(request):
        calls.append(json.loads(request.content)["from"])
        hits = [{"_id": "x", "_source": {}}] if len(calls) == 1 else []
        return httpx.Response(200, json={"hits": {"hits": hits}})

    with httpx.Client(transport=transport(handle)) as client:
        assert len(list(aon.fetch_category(client, "feat"))) == 1
    assert calls == [0, 1]


def test_aon_post_retries_then_raises(monkeypatch):
    monkeypatch.setattr(aon.time, "sleep", lambda s: None)
    attempts = []

    def flaky(request):
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"aggregations": {"cats": {"buckets": []}}})

    with httpx.Client(transport=transport(flaky)) as client:
        assert aon.categories(client) == []
    assert len(attempts) == 3

    def always_bad(request):
        return httpx.Response(200, content=b"not json")

    with httpx.Client(transport=transport(always_bad)) as client, pytest.raises(orjson.JSONDecodeError):
        aon.categories(client)


# --- PathfinderWiki ---------------------------------------------------------------

def test_wiki_site_info_and_pages(monkeypatch):
    monkeypatch.setattr(wiki.time, "sleep", lambda s: None)
    seen = []

    def handle(request):
        params = dict(request.url.params)
        assert params["format"] == "json" and params["formatversion"] == "2"
        seen.append(params)
        if params.get("meta") == "siteinfo":
            return httpx.Response(200, json={"query": {"statistics": {"pages": 3}}})
        if "gapcontinue" not in params:
            return httpx.Response(200, json={
                "query": {"pages": [
                    {"title": "Cheliax", "pageid": 1, "revisions": [
                        {"revid": 9, "timestamp": "t", "slots": {"main": {"content": "text"}}}]},
                    {"title": "No revs", "pageid": 2},
                    {"title": "No content", "pageid": 3, "revisions": [{"slots": {"main": {}}}]},
                ]},
                "continue": {"gapcontinue": "D", "continue": "gapcontinue||"}})
        return httpx.Response(200, json={"query": {"pages": [
            {"title": "Desna", "pageid": 4, "revisions": [
                {"revid": 10, "timestamp": "t2", "slots": {"main": {"content": "more"}}}]}]}})

    with httpx.Client(transport=transport(handle)) as client:
        assert wiki.site_info(client) == {"statistics": {"pages": 3}}
        pages = list(wiki.iter_pages(client))
    assert [p["title"] for p in pages] == ["Cheliax", "Desna"]
    assert pages[0] == {"title": "Cheliax", "pageid": 1, "revid": 9, "timestamp": "t",
                        "wikitext": "text"}
    assert seen[-1]["gapcontinue"] == "D"


def test_wiki_get_gives_up_after_five(monkeypatch):
    monkeypatch.setattr(wiki.time, "sleep", lambda s: None)
    calls = []

    def down(request):
        calls.append(1)
        return httpx.Response(500)

    with httpx.Client(transport=transport(down)) as client, pytest.raises(httpx.HTTPStatusError):
        wiki.site_info(client)
    assert len(calls) == 5


# --- model clients ------------------------------------------------------------------

def sse(*chunks):
    return "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"


def test_openai_compatible_client():
    seen = []

    def handle(request):
        seen.append(request)
        if request.url.path == "/v1/embeddings":
            return httpx.Response(200, json={"data": [{"embedding": [3.0, 4.0]},
                                                      {"embedding": [0.0, 0.0]}]})
        if request.url.path == "/v1/chat/completions":
            if json.loads(request.content)["stream"]:
                return httpx.Response(200, text=sse(
                    {"choices": [{"delta": {"content": "Hel"}}]},
                    {"choices": [{"delta": {}}]},
                    {"choices": [{"delta": {"content": "lo"}}]}))
            return httpx.Response(200, json={"choices": [{"message": {"content": " hi "}}]})
        return httpx.Response(404, text="nope")

    c = OpenAICompatible("http://lm:1234/v1/", api_key="sk-test")
    assert c.base_url == "http://lm:1234"
    c._client = httpx.Client(transport=transport(handle),
                             headers={"Authorization": "Bearer sk-test"})
    vecs = c.embed(["a", "b"], "emb")
    assert np.allclose(vecs, [[0.6, 0.8], [0.0, 0.0]])
    assert seen[0].headers["Authorization"] == "Bearer sk-test"
    assert c.chat("sys", "usr", "m", max_tokens=5) == "hi"
    body = json.loads(seen[1].content)
    assert body["messages"][0] == {"role": "system", "content": "sys"} and body["max_tokens"] == 5
    assert list(c.stream("s", "u", "m")) == ["Hel", "lo"]
    with pytest.raises(OllamaError, match="returned 404"):
        c._post("/v1/other", {})
    c.close()


def test_openai_compatible_errors():
    c = OpenAICompatible("http://lm:1234")

    def refuse(request):
        raise httpx.ConnectError("refused")

    c._client = httpx.Client(transport=transport(refuse))
    with pytest.raises(OllamaError, match="Cannot reach"):
        c.chat("s", "u", "m")
    with pytest.raises(OllamaError, match="Cannot reach"):
        list(c.stream("s", "u", "m"))
    c._client = httpx.Client(transport=transport(lambda r: httpx.Response(401)))
    with pytest.raises(OllamaError, match="returned 401"):
        list(c.stream("s", "u", "m"))


def test_ollama_client():
    def handle(request):
        body = json.loads(request.content)
        if body["model"] == "missing":
            return httpx.Response(404)
        if request.url.path == "/api/embed":
            assert body["input"] == ["x"]
            return httpx.Response(200, json={"embeddings": [[0.0, 2.0]]})
        if body["stream"]:
            lines = [{"message": {"content": "a"}}, {"message": {}},
                     {"message": {"content": "b"}, "done": True},
                     {"message": {"content": "never"}}]
            return httpx.Response(200, text="\n".join(json.dumps(line) for line in lines))
        assert body["think"] is False and body["options"] == {"temperature": 0, "num_predict": 9}
        return httpx.Response(200, json={"message": {"content": " ok "}})

    c = Ollama("http://ollama:11434/")
    assert c.base_url == "http://ollama:11434"
    c._client = httpx.Client(transport=transport(handle))
    assert np.allclose(c.embed(["x"], "emb"), [[0.0, 1.0]])
    assert c.chat("s", "u", "m", max_tokens=9) == "ok"
    assert list(c.stream("s", "u", "m")) == ["a", "b"]
    with pytest.raises(OllamaError, match="ollama pull missing"):
        c.chat("s", "u", "missing")
    with pytest.raises(OllamaError, match="ollama pull missing"):
        list(c.stream("s", "u", "missing"))

    def refuse(request):
        raise httpx.ConnectError("refused")

    c._client = httpx.Client(transport=transport(refuse))
    with pytest.raises(OllamaError, match="ollama serve"):
        c.embed(["x"], "emb")
    with pytest.raises(OllamaError, match="ollama serve"):
        list(c.stream("s", "u", "m"))
    c._client = httpx.Client(transport=transport(lambda r: httpx.Response(500)))
    with pytest.raises(httpx.HTTPStatusError):
        c.chat("s", "u", "m")
    c.close()


def test_client_for():
    o = client_for("ollama", "http://a:1/")
    assert isinstance(o, Ollama) and o.base_url == "http://a:1"
    o.close()
    p = client_for("openai", "http://b:2/v1", api_key="k")
    assert isinstance(p, OpenAICompatible) and p.base_url == "http://b:2"
    p.close()


def test_probe_backend(monkeypatch):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append((url, headers))
        if url.endswith("/v1/models"):
            return httpx.Response(200, json={"data": [{"id": "b"}, {"id": "a"}, "junk", {}]})
        if url.endswith("/api/tags"):
            return httpx.Response(200, json={"models": [{"name": "qwen3.5:4b"}, {"nope": 1}]})
        if url.endswith("/denied/api/tags"):
            return httpx.Response(401)
        return httpx.Response(200, content=b"<html>")

    monkeypatch.setattr(httpx, "get", fake_get)
    assert probe_backend("openai", "http://lm/v1/", api_key="k") == ["a", "b"]
    assert calls[0] == ("http://lm/v1/models", {"Authorization": "Bearer k"})
    assert probe_backend("ollama", "http://o:11434/") == ["qwen3.5:4b"]
    assert calls[1][1] == {}

    def denied(url, headers=None, timeout=None):
        return httpx.Response(403)

    monkeypatch.setattr(httpx, "get", denied)
    with pytest.raises(OllamaError, match="check the API key"):
        probe_backend("openai", "http://lm")

    monkeypatch.setattr(httpx, "get", lambda url, headers=None, timeout=None:
                        httpx.Response(200, content=b"<html>"))
    with pytest.raises(OllamaError, match="did not return JSON"):
        probe_backend("ollama", "http://o")

    def unreachable(url, headers=None, timeout=None):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", unreachable)
    with pytest.raises(OllamaError, match="Cannot reach"):
        probe_backend("ollama", "http://o")
