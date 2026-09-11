"""The MCP transport: JSON-RPC lines in, one line per request out."""

import io
import json
import sys

from conftest import plan_reply

from kleverkobold import mcp_server


def run(monkeypatch, assistant, requests):
    monkeypatch.setattr(mcp_server, "Assistant", lambda *a, **k: assistant)
    stdin = io.TextIOWrapper(io.BytesIO(b"".join(
        (r if isinstance(r, bytes) else json.dumps(r).encode()) + b"\n" for r in requests)))
    out = io.BytesIO()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(out))
    mcp_server.serve(None, "http://fake:1")
    sys.stdout.flush()
    return [json.loads(line) for line in out.getvalue().decode().splitlines() if line]


def test_initialize_and_list(monkeypatch, assistant):
    replies = run(monkeypatch, assistant, [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "nothing/here"},
        b"not json at all",
        b"",
    ])
    assert [r["id"] for r in replies] == [1, 2, 3]
    assert replies[0]["result"]["serverInfo"]["name"] == "kleverkobold"
    names = {t["name"] for t in replies[1]["result"]["tools"]}
    assert names == {"kobold_ask", "kobold_search", "kobold_entry"}
    assert replies[2]["error"]["code"] == -32601


def test_tool_calls(monkeypatch, assistant, client):
    # search: rewrite, rerank.  ask: rewrite, rerank, answer.
    client.replies = [plan_reply("prone", "condition"), "1",
                      plan_reply("treat wounds", "action"), "1", "Ten minutes."]
    replies = run(monkeypatch, assistant, [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "kobold_search", "arguments": {"question": "prone", "k": 2}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "kobold_ask", "arguments": {"question": "treat wounds", "k": 1}}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "kobold_ask", "arguments": {"question": "   "}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "kobold_ask", "arguments": {"question": "q", "scope": "wide"}}},
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
         "params": {"name": "kobold_dance", "arguments": {"question": "q"}}},
    ])
    search = replies[0]["result"]
    assert search["isError"] is False and "## Prone (condition)" in search["content"][0]["text"]
    ask = replies[1]["result"]["content"][0]["text"]
    assert ask.startswith("Ten minutes.\n\nSources:\n- ")
    assert replies[2]["result"]["isError"] and "required" in replies[2]["result"]["content"][0]["text"]
    assert replies[3]["result"]["isError"] and "scope" in replies[3]["result"]["content"][0]["text"]
    assert "Unknown tool" in replies[4]["result"]["content"][0]["text"]


def test_tool_failures_keep_the_transport_alive(monkeypatch, assistant, client):
    def boom(*a, **k):
        raise RuntimeError("kaput")

    client.embed = boom      # a chat failure is absorbed by the rewrite step; embedding is not
    replies = run(monkeypatch, assistant, [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "kobold_search", "arguments": {"question": "prone"}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ])
    assert replies[0]["result"]["isError"] and "RuntimeError: kaput" in \
        replies[0]["result"]["content"][0]["text"]
    assert "tools" in replies[1]["result"]


def test_search_tool_filters_and_lists(monkeypatch, assistant, client):
    client.replies = [plan_reply()]
    replies = run(monkeypatch, assistant, [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "kobold_search", "arguments": {"kinds": ["feat", "action"]}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "kobold_search", "arguments": {"question": "medicine", "traits": ["skill"]}}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "kobold_search", "arguments": {"level": "abc"}}},
    ])
    listing = replies[0]["result"]["content"][0]["text"]
    assert listing.startswith("- Battle Medicine (feat, level 1)") and "Treat Wounds (action)" in listing
    assert "## Battle Medicine" in replies[1]["result"]["content"][0]["text"]
    assert replies[2]["result"]["isError"]


def test_ask_tool_takes_a_persona(monkeypatch, assistant, client):
    client.replies = [plan_reply(), "1", "Yes."]
    run(monkeypatch, assistant, [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "kobold_ask", "arguments": {"question": "prone?", "k": 1,
                                                        "persona": "level 2 wizard"}}}])
    assert "The person asking plays: level 2 wizard" in client.calls[-1][1]


def test_entry_tool(monkeypatch, assistant):
    replies = run(monkeypatch, assistant, [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "kobold_entry", "arguments": {"name": "Gurglegut"}}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "kobold_entry", "arguments": {"url": "https://pathfinderwiki.com/wiki/Cheliax"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "kobold_entry", "arguments": {"name": "Nothing Here"}}},
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
         "params": {"name": "kobold_entry", "arguments": {}}},
    ])
    assert "kobold_entry" in {t["name"] for t in replies[0]["result"]["tools"]}
    text = replies[1]["result"]["content"][0]["text"]
    assert text.startswith("## Gurglegut (creature, level 12)\nhttps://") and "swamp dragon" in text
    assert "Golarion lore" in replies[2]["result"]["content"][0]["text"]
    assert replies[3]["result"]["isError"] and "Nothing Here" in replies[3]["result"]["content"][0]["text"]
    assert replies[4]["result"]["isError"]
