#!/usr/bin/env bash
# One-command setup. Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v ollama >/dev/null || { echo "Install Ollama first: brew install ollama"; exit 1; }
curl -sf http://localhost:11434/api/tags >/dev/null || {
  echo "Ollama is not responding. Start it (ollama serve, or open Ollama.app) and re-run."; exit 1; }

for model in qwen3.5:9b qwen3-embedding:0.6b; do
  ollama list | grep -q "^${model%%:*}" || ollama pull "$model"
done

[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r deploy/requirements.txt

if [ ! -d dist/pf2e-index ]; then
  echo "Fetching the packaged index (143 MB)..."
  mkdir -p dist
  if command -v gh >/dev/null; then
    gh release download index-v1 --pattern 'pf2e-index.tar.gz' --clobber -O /tmp/pf2e-index.tar.gz
  else
    curl -fL -o /tmp/pf2e-index.tar.gz \
      https://github.com/DeastinY/pf2etune/releases/download/index-v1/pf2e-index.tar.gz
  fi
  tar -xzf /tmp/pf2e-index.tar.gz -C dist
fi

PYTHONPATH=src .venv/bin/python -m pf2etune doctor
