"""Knowing when a newer kobold is out, and fetching it.

The program is installed from git (``uv tool install git+…``), so a version
is a commit. pip and uv record the commit they installed in the package's
``direct_url.json`` (PEP 610); the newest is one anonymous request to GitHub
for the tip of ``main``. The check sends nothing but that request -- nothing
typed leaves the machine -- and ``--no-update-check`` turns it off.

Upgrading is ``uv tool upgrade kleverkobold`` and a restart, which the server
can do to itself: the page asks, the command runs, the process re-executes
and the page reloads once it answers again. Only a browser on the same
machine may ask, since the request runs a command on the host.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

import httpx
import orjson

REPO = "DeastinY/klever-kobold"
API = f"https://api.github.com/repos/{REPO}/commits/main"
PACKAGE = "kleverkobold"
# Set by restart() so a freshly upgraded process does not upgrade again on
# start, whatever the check says.
JUST_UPGRADED = "KOBOLD_JUST_UPGRADED"


def _direct_url() -> dict | None:
    try:
        from importlib.metadata import distribution
        raw = distribution(PACKAGE).read_text("direct_url.json")
    except Exception:
        return None
    if not raw:
        return None
    try:
        return orjson.loads(raw)
    except orjson.JSONDecodeError:
        return None


def is_tool_install() -> bool:
    """Installed from git by pip or uv, as opposed to run from a checkout."""
    info = _direct_url() or {}
    return bool((info.get("vcs_info") or {}).get("commit_id"))


def installed_commit() -> str | None:
    info = _direct_url() or {}
    commit = (info.get("vcs_info") or {}).get("commit_id")
    if commit:
        return commit
    root = pathlib.Path(__file__).resolve().parents[2]
    if (root / ".git").exists():
        try:
            out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                 capture_output=True, text=True, timeout=5)
            return out.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            return None
    return None


def latest_commit(timeout: float = 6.0) -> dict | None:
    """The tip of main: sha, date and the first line of its message."""
    r = httpx.get(API, timeout=timeout,
                  headers={"Accept": "application/vnd.github+json", "User-Agent": PACKAGE})
    if r.status_code != 200:
        return None
    data = orjson.loads(r.content)
    commit = data.get("commit") or {}
    return {"sha": data.get("sha") or "",
            "date": ((commit.get("committer") or {}).get("date") or "")[:10],
            "message": (commit.get("message") or "").split("\n", 1)[0][:120]}


def check(timeout: float = 6.0) -> dict:
    """What is installed, what is out, and whether the first is behind the second.

    Never raises: offline, rate-limited or unknown all come back as
    ``checked: False`` and the page says nothing.
    """
    current = installed_commit() or ""
    out = {"checked": False, "current": current[:7], "latest": "", "date": "", "message": "",
           "behind": False, "tool": is_tool_install(), "command": " ".join(upgrade_command() or [])}
    try:
        latest = latest_commit(timeout)
    except Exception:
        latest = None
    if not latest or not latest["sha"]:
        return out
    out.update(checked=True, latest=latest["sha"][:7], date=latest["date"],
               message=latest["message"], behind=bool(current) and current != latest["sha"])
    return out


def upgrade_command() -> list[str] | None:
    """How this install is upgraded, or None when it is a checkout."""
    if not is_tool_install():
        return None
    uv = shutil.which("uv")
    if not uv:
        home = pathlib.Path.home() / ".local" / "bin" / ("uv.exe" if os.name == "nt" else "uv")
        uv = str(home) if home.exists() else "uv"
    return [uv, "tool", "upgrade", PACKAGE]


def upgrade(timeout: float = 600.0) -> tuple[bool, str]:
    """Run the upgrade. Returns (ok, the command's output, trimmed)."""
    cmd = upgrade_command()
    if not cmd:
        return False, ("This kobold runs from a checkout, not an installed tool; "
                       "update it with `git pull` and restart.")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{' '.join(cmd)}: {type(exc).__name__}: {exc}"
    out = (r.stdout + "\n" + r.stderr).strip()
    return r.returncode == 0, out[-2000:]


def restart() -> None:
    """Replace this process with a fresh one running the same command line."""
    os.environ[JUST_UPGRADED] = "1"
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(sys.executable, [sys.executable, "-m", PACKAGE, *sys.argv[1:]])


# --- the one setting that lives on the server -------------------------------

def config_path() -> pathlib.Path:
    from .app import data_home
    return data_home() / "config.json"


def read_config() -> dict:
    try:
        return orjson.loads(config_path().read_bytes())
    except (OSError, orjson.JSONDecodeError):
        return {}


def write_config(**values) -> dict:
    cfg = read_config()
    cfg.update(values)
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(orjson.dumps(cfg, option=orjson.OPT_INDENT_2))
    return cfg


def auto_upgrade() -> bool:
    return bool(read_config().get("auto_upgrade"))
