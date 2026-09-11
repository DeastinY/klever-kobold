"""The abstention-data script's teacher over HTTP: order, retries, and the server's dialect."""

import importlib.util
import json
import pathlib
import sys

import httpx
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
for sub in ("scripts", "eval"):
    if str(ROOT / sub) not in sys.path:
        sys.path.insert(0, str(ROOT / sub))


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("make_abstention_data",
                                                  ROOT / "scripts" / "make_abstention_data.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def server(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def reply(text):
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


def test_results_come_back_in_prompt_order(script, monkeypatch):
    seen = []

    def handle(request):
        body = json.loads(request.content)
        seen.append(body)
        user = body["messages"][1]["content"]
        return reply(f"<think>hmm</think>answer to {user}")

    gen = script.api_generator("http://teacher/v1", "qwen", api_key="k", workers=4,
                               client=server(handle))
    pairs = [("sys", f"q{i}") for i in range(9)]
    out = gen(pairs, 70)
    assert out == [f"answer to q{i}" for i in range(9)]           # thinking stripped, order kept
    body = seen[0]
    assert body["model"] == "qwen" and body["temperature"] == 0 and body["max_tokens"] == 70
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["messages"][0] == {"role": "system", "content": "sys"}


def test_learns_the_servers_dialect(script, monkeypatch):
    monkeypatch.setattr(script.time, "sleep", lambda s: None)
    calls = []

    def handle(request):
        body = json.loads(request.content)
        calls.append(body)
        if "chat_template_kwargs" in body:
            return httpx.Response(400, text="unknown field chat_template_kwargs")
        if "max_tokens" in body:
            return httpx.Response(400, text="use max_completion_tokens instead of max_tokens")
        return reply("fine")

    gen = script.api_generator("http://teacher/v1/", "m", workers=1, client=server(handle))
    assert gen([("s", "a"), ("s", "b")], 10) == ["fine", "fine"]
    # Learned once: the second prompt goes straight through in the right dialect.
    assert "chat_template_kwargs" not in calls[-1] and calls[-1]["max_completion_tokens"] == 10
    assert len(calls) == 4


def test_retries_then_gives_up(script, monkeypatch):
    monkeypatch.setattr(script.time, "sleep", lambda s: None)
    n = {"calls": 0}

    def flaky(request):
        n["calls"] += 1
        return httpx.Response(503, text="busy") if n["calls"] < 3 else reply("ok")

    gen = script.api_generator("http://t/v1", "m", workers=1, client=server(flaky))
    assert gen([("s", "u")], 5) == ["ok"] and n["calls"] == 3

    def refuse(request):
        return httpx.Response(401, text="who are you")

    gen = script.api_generator("http://t/v1", "m", workers=1, client=server(refuse))
    with pytest.raises(RuntimeError, match="HTTP 401"):
        gen([("s", "u")], 5)

    def always_busy(request):
        return httpx.Response(503, text="busy")

    gen = script.api_generator("http://t/v1", "m", workers=1, client=server(always_busy))
    with pytest.raises(RuntimeError, match="giving up"):
        gen([("s", "u")], 5)


def test_regexes_still_defined(script):
    assert script.RE_CORRECTS.search("That is a D&D 5e mechanic, not Pathfinder.")
    assert script.asserts_level_for("Shoony Lore is a 4th-level feat.", "Shoony Lore")
