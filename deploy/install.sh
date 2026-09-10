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

if [ ! -d dist/kobold-index ]; then
  echo "Fetching the packaged index (143 MB)..."
  mkdir -p dist
  if command -v gh >/dev/null; then
    gh release download index-v1 --pattern 'kobold-index.tar.gz' --clobber -O /tmp/kobold-index.tar.gz
  else
    curl -fL -o /tmp/kobold-index.tar.gz \
      https://github.com/DeastinY/klever-kobold/releases/download/index-v1/kobold-index.tar.gz
  fi
  tar -xzf /tmp/kobold-index.tar.gz -C dist
fi

PYTHONPATH=src .venv/bin/python -m kleverkobold doctor
