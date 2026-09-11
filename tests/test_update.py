"""Knowing what is installed, what is out, and how to move between them."""

import subprocess
import sys

import httpx
import orjson
import pytest

from kleverkobold import update


class Dist:
    def __init__(self, text):
        self.text = text

    def read_text(self, name):
        assert name == "direct_url.json"
        return self.text


def tool_install(monkeypatch, sha="c8981c22b75a24314c349226ad7dcae7a537e8c2"):
    import importlib.metadata
    monkeypatch.setattr(importlib.metadata, "distribution",
                        lambda name: Dist(orjson.dumps({"url": "https://github.com/x/y",
                                                        "vcs_info": {"vcs": "git", "commit_id": sha}}).decode()))


def test_installed_commit_from_direct_url(monkeypatch):
    tool_install(monkeypatch)
    assert update.installed_commit().startswith("c8981c2")
    assert update.is_tool_install() is True
    assert update.upgrade_command()[1:] == ["tool", "upgrade", "kleverkobold"]


def test_checkout_asks_git(monkeypatch):
    import importlib.metadata
    monkeypatch.setattr(importlib.metadata, "distribution", lambda name: Dist(None))
    assert update.is_tool_install() is False
    assert update.upgrade_command() is None
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "abc123\n", ""))
    assert update.installed_commit() == "abc123"
    ok, msg = update.upgrade()
    assert ok is False and "git pull" in msg


def test_bad_direct_url_is_ignored(monkeypatch):
    import importlib.metadata
    monkeypatch.setattr(importlib.metadata, "distribution", lambda name: Dist("not json"))
    assert update.is_tool_install() is False


def fake_github(monkeypatch, sha="ffffff0000000000000000000000000000000000", status=200):
    calls = []

    def get(url, timeout=None, headers=None):
        calls.append((url, headers))
        return httpx.Response(status, json={"sha": sha, "commit": {
            "committer": {"date": "2026-09-11T10:00:00Z"},
            "message": "A newer kobold\n\nwith a body"}})

    monkeypatch.setattr(httpx, "get", get)
    return calls


def test_latest_commit(monkeypatch):
    calls = fake_github(monkeypatch)
    latest = update.latest_commit()
    assert latest == {"sha": "ffffff0000000000000000000000000000000000", "date": "2026-09-11",
                      "message": "A newer kobold"}
    assert calls[0][0] == update.API and calls[0][1]["User-Agent"] == "kleverkobold"
    fake_github(monkeypatch, status=403)
    assert update.latest_commit() is None


def test_check_behind_and_current(monkeypatch):
    tool_install(monkeypatch, sha="aaaaaaa0000000000000000000000000000000000")
    fake_github(monkeypatch)
    seen = update.check()
    assert seen["checked"] and seen["behind"] and seen["current"] == "aaaaaaa"
    assert seen["latest"] == "ffffff0" and seen["tool"] and "tool upgrade" in seen["command"]
    fake_github(monkeypatch, sha="aaaaaaa0000000000000000000000000000000000")
    assert update.check()["behind"] is False


def test_check_never_raises(monkeypatch):
    tool_install(monkeypatch)

    def down(*a, **k):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "get", down)
    seen = update.check()
    assert seen["checked"] is False and seen["behind"] is False and seen["current"]


def test_upgrade_runs_the_command(monkeypatch):
    tool_install(monkeypatch)
    seen = {}

    def run(cmd, capture_output, text, timeout):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "Updated kleverkobold\n", "")

    monkeypatch.setattr(subprocess, "run", run)
    ok, out = update.upgrade()
    assert ok and out == "Updated kleverkobold" and seen["cmd"][1:] == ["tool", "upgrade", "kleverkobold"]

    def fail(cmd, **k):
        raise OSError("no uv")

    monkeypatch.setattr(subprocess, "run", fail)
    ok, out = update.upgrade()
    assert not ok and "OSError" in out


def test_restart_execs_the_same_command_line(monkeypatch):
    import os
    seen = {}
    monkeypatch.setattr(os, "execv", lambda exe, argv: seen.update(exe=exe, argv=argv))
    monkeypatch.setattr(sys, "argv", ["/x/bin/kobold", "serve", "--port", "1"])
    monkeypatch.delenv(update.JUST_UPGRADED, raising=False)
    update.restart()
    assert seen["exe"] == sys.executable
    assert seen["argv"] == [sys.executable, "-m", "kleverkobold", "serve", "--port", "1"]
    assert os.environ[update.JUST_UPGRADED] == "1"


def test_config_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(update, "config_path", lambda: tmp_path / "deep" / "config.json")
    assert update.read_config() == {} and update.auto_upgrade() is False
    assert update.write_config(auto_upgrade=True) == {"auto_upgrade": True}
    assert update.auto_upgrade() is True
    (tmp_path / "deep" / "config.json").write_text("garbage")
    assert update.read_config() == {}


@pytest.mark.parametrize("platform, env, want", [
    ("linux", {"XDG_DATA_HOME": "/xdg"}, "/xdg/kleverkobold"),
    ("darwin", {}, "Library/Application Support/kleverkobold"),
])
def test_data_home(monkeypatch, platform, env, want):
    from kleverkobold import app
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert str(app.data_home()).endswith(want)
