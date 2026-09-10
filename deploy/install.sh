#!/usr/bin/env sh
# The Klever Kobold — one-line install for macOS and Linux. Safe to re-run.
#
#   curl -fsSL https://raw.githubusercontent.com/DeastinY/klever-kobold/main/deploy/install.sh | sh
#
# Installs uv (the Python tool runner) and Ollama if missing, then the kobold,
# then pulls the two models and the rules index, and opens it in the browser.
set -eu

REPO="${KOBOLD_REPO:-https://github.com/DeastinY/klever-kobold}"
say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }
OS=$(uname -s)

say "1/4  uv"
if ! have uv; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
uv --version

say "2/4  Ollama"
if ! have ollama; then
  case "$OS" in
    Darwin)
      if have brew; then brew install ollama
      else
        echo "Homebrew is not installed. Get Ollama from https://ollama.com/download, open it once,"
        echo "then run this installer again."; exit 1
      fi ;;
    Linux) curl -fsSL https://ollama.com/install.sh | sh ;;
    *) echo "Unsupported system: $OS. See https://ollama.com/download"; exit 1 ;;
  esac
fi
if ! curl -sf http://localhost:11434/api/tags >/dev/null; then
  case "$OS" in
    Darwin) (have brew && brew services start ollama) || (nohup ollama serve >/dev/null 2>&1 &) ;;
    Linux)  (have systemctl && sudo systemctl start ollama) || (nohup ollama serve >/dev/null 2>&1 &) ;;
  esac
  sleep 2
fi
ollama --version

say "3/4  The Klever Kobold"
uv tool install --force "git+$REPO"
export PATH="$HOME/.local/bin:$PATH"
kobold setup            # both models (about 4 GB) and the rules index (150 MB); idempotent

say "4/4  Starting"
echo "Runs at http://localhost:8765 — next time, just:  kobold serve"
case "$OS" in
  Darwin) (sleep 3; open http://localhost:8765) & ;;
  Linux)  (sleep 3; xdg-open http://localhost:8765 >/dev/null 2>&1 || true) & ;;
esac
exec kobold serve
