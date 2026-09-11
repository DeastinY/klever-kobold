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


# --- doctor and setup: every moving part faked, so the commands run to the end ---

class FakeResponse:
    def __init__(self, payload=None, lines=(), content=b""):
        self.payload, self.lines, self.content = payload, list(lines), content
        self.headers = {"content-length": str(len(content))}
        self.status_code = 200

    def json(self):
        return self.payload

    def raise_for_status(self):
        pass

    def iter_lines(self):
        yield from self.lines

    def iter_bytes(self, n):
        for i in range(0, len(self.content), n):
            yield self.content[i:i + n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOllama:
    fail = None

    def __init__(self, url, timeout=None):
        self.url = url

    def embed(self, texts, model):
        if self.fail == "embed":
            from kleverkobold.app import OllamaError
            raise OllamaError("no encoder")
        return [[0.0]]

    def chat(self, system, user, model, max_tokens=8):
        return "ok"


def test_doctor_reports_every_part(monkeypatch, index_dir, assistant, capsys):
    import httpx
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/ollama")
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None: FakeResponse({"version": "0.19.0"}))
    monkeypatch.setattr(cli, "Ollama", FakeOllama)
    monkeypatch.setattr(cli, "_assistant", lambda args: assistant)
    assert cli.main(["--index", str(index_dir), "doctor"]) == 0
    out = capsys.readouterr().out
    assert "ok   manifest.json" in out and "ok   ollama_llm" in out
    assert "retrieval smoke test ->" in out and "lore smoke test" in out and "all good" in out


def test_doctor_names_the_broken_part(monkeypatch, index_dir, tmp_path, capsys):
    import httpx
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/ollama")
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None: FakeResponse({"version": "0.19.0"}))
    monkeypatch.setattr(FakeOllama, "fail", "embed")
    monkeypatch.setattr(cli, "Ollama", FakeOllama)
    assert cli.main(["--index", str(index_dir), "doctor"]) == 1
    out = capsys.readouterr().out
    assert "FAIL ollama_embed" in out and "no encoder" in out
    # No index at all: says which files are missing, and how to get them.
    assert cli.main(["--index", str(tmp_path / "empty"), "doctor"]) == 1
    assert "MISSING" in capsys.readouterr().out


def test_doctor_without_ollama_installed(monkeypatch, index_dir, capsys):
    import httpx
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)

    def down(url, timeout=None):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", down)
    assert cli.main(["--index", str(index_dir), "doctor"]) == 1
    assert "Ollama is not installed" in capsys.readouterr().out


def test_setup_with_everything_present(monkeypatch, index_dir, capsys):
    import httpx
    monkeypatch.setattr(cli, "ensure_ollama", lambda url, install: True)
    monkeypatch.setattr(cli, "default_llm", lambda: ("qwen3.5:4b", "the default"))
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None: FakeResponse(
        {"models": [{"name": "qwen3-embedding:0.6b"}, {"name": "qwen3.5:4b"}]}))
    assert cli.main(["--index", str(index_dir), "setup"]) == 0
    out = capsys.readouterr().out
    assert "ok   qwen3.5:4b" in out and "already present" in out and "ready:  kobold serve" in out


def test_setup_pulls_and_unpacks(monkeypatch, index_dir, tmp_path, capsys):
    import io
    import tarfile

    import httpx

    from kleverkobold.app import INDEX_URL
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(index_dir, arcname="kobold-index")
    tarball = buf.getvalue()
    monkeypatch.setattr(cli, "ensure_ollama", lambda url, install: True)
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None: FakeResponse({"models": []}))
    seen = []

    def stream(method, url, **kw):
        seen.append((method, url))
        if url == INDEX_URL:
            return FakeResponse(content=tarball)
        return FakeResponse(lines=['{"status":"pulling manifest"}', '', '{"status":"success"}'])

    monkeypatch.setattr(httpx, "stream", stream)
    target = tmp_path / "data" / "kobold-index"
    assert cli.main(["--index", str(target), "setup", "--llm-model", "qwen3.5:4b"]) == 0
    out = capsys.readouterr().out
    assert "pulling qwen3-embedding:0.6b" in out and "pulling qwen3.5:4b (~3.4 GB)" in out
    assert "pulling manifest" in out and "ok   unpacked" in out
    assert (target / "manifest.json").exists() and (target / "bm25.npz").exists()
    assert [m for m, _ in seen] == ["POST", "POST", "GET"]


def test_setup_says_when_the_index_cannot_be_fetched(monkeypatch, tmp_path, capsys):
    import httpx
    monkeypatch.setattr(cli, "ensure_ollama", lambda url, install: True)
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None: FakeResponse(
        {"models": [{"name": "qwen3-embedding:0.6b"}, {"name": "qwen3.5:4b"}]}))

    class Gone(FakeResponse):
        def __init__(self):
            super().__init__()
            self.status_code = 404

        def raise_for_status(self):
            raise httpx.HTTPStatusError("404", request=None, response=self)

    monkeypatch.setattr(httpx, "stream", lambda method, url, **kw: Gone())
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert cli.main(["--index", str(tmp_path / "idx"), "setup", "--llm-model", "qwen3.5:4b"]) == 1
    assert "cannot be fetched anonymously" in capsys.readouterr().err


def test_ensure_ollama_paths(monkeypatch, capsys):
    import httpx
    calls = {"n": 0}

    def get(url, timeout=None):
        calls["n"] += 1
        if calls["n"] > 2:
            return FakeResponse({})
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", get)
    # Not installed, not allowed to install: says how.
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    assert cli.ensure_ollama(cli.DEFAULT_OLLAMA, install=False) is False
    assert "not installed" in capsys.readouterr().err
    # Installed but down on the default endpoint: started, then answers.
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/ollama")
    started = []
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *a, **k: started.append(a[0]))
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)
    calls["n"] = 0
    assert cli.ensure_ollama(cli.DEFAULT_OLLAMA, install=False) is True
    assert started == [["ollama", "serve"]]
    # Down on a custom endpoint: not ours to start.
    calls["n"] = -100
    assert cli.ensure_ollama("http://elsewhere:9999", install=False) is False
    assert "nothing is answering" in capsys.readouterr().err
