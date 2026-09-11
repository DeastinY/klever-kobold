"""The command line: argument parsing and the commands that need no model to answer."""

import pytest

from conftest import plan_reply
from kleverkobold import __main__ as cli


def test_help_and_missing_arguments(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert "kobold" in capsys.readouterr().out
    with pytest.raises(SystemExit) as exc:
        cli.main(["ask"])
    assert exc.value.code == 2
    with pytest.raises(SystemExit):
        cli.main(["ask", "q", "--scope", "everything"])


def test_llm_choice_respects_overrides(capsys):
    class Args:
        llm_override = "custom"
        backend = "ollama"

    assert cli._llm(Args()) == ("custom", False)

    class OpenAI:
        llm_override = None
        backend = "openai"

    assert cli._llm(OpenAI()) == (None, False)

    class Auto:
        llm_override = None
        backend = "ollama"

    model, auto = cli._llm(Auto())
    assert auto is True and model.startswith("qwen3.5:")
    assert "answering model" in capsys.readouterr().err


def test_search_command_prints_hits(monkeypatch, assistant, client, capsys):
    monkeypatch.setattr(cli, "_assistant", lambda args: assistant)
    client.replies = [plan_reply("prone condition", "condition")]
    assert cli.main(["search", "what does prone do", "-k", "2", "--no-rerank"]) == 0
    out = capsys.readouterr().out
    assert "interpreted as: 'prone condition'  kinds=['condition']  scope=rules" in out
    assert "1. Prone [condition]" in out


def test_ask_command_json(monkeypatch, assistant, client, capsys):
    import json
    monkeypatch.setattr(cli, "_assistant", lambda args: assistant)
    client.replies = [plan_reply("cheliax", "", "lore"), "House Thrune."]
    assert cli.main(["ask", "who rules Cheliax", "--json", "--no-rerank", "--scope", "auto"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["answer"] == "House Thrune." and payload["scope"] == "lore"
    assert "hits" not in payload and payload["sources"]
