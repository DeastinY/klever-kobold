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

[ -d dist/pf2e-index ] || {
  echo
  echo "No index found at dist/pf2e-index."
  echo "Copy it from a machine that has one, or build it:"
  echo "  .venv/bin/python scripts/dump_aon.py && .venv/bin/python scripts/build_chunks.py"
  exit 1; }

PYTHONPATH=src .venv/bin/python -m pf2etune doctor
