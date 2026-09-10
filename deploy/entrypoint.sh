#!/usr/bin/env bash
# Provision on first run so `docker compose up` is genuinely one command:
# wait for Ollama, pull the two models if absent, fetch the index if absent.
set -euo pipefail

INDEX="${KOBOLD_INDEX:-/data/kobold-index}"
OLLAMA="${OLLAMA_URL:-http://ollama:11434}"
LLM="${PF2E_LLM:-qwen3.5:9b}"
EMBED="${PF2E_EMBED:-qwen3-embedding:0.6b}"

echo "waiting for Ollama at $OLLAMA ..."
for _ in $(seq 1 120); do
  curl -sf "$OLLAMA/api/tags" >/dev/null && break
  sleep 2
done
curl -sf "$OLLAMA/api/tags" >/dev/null || { echo "Ollama never became ready at $OLLAMA"; exit 1; }

have() { curl -sf "$OLLAMA/api/tags" | grep -q "\"$1\""; }
for model in "$EMBED" "$LLM"; do
  if have "$model"; then
    echo "model present: $model"
  else
    echo "pulling $model (first run only; the 9B is ~5.7 GB)"
    curl -sf -X POST "$OLLAMA/api/pull" -d "{\"model\":\"$model\"}" \
      | grep -o '"status":"[^"]*"' | uniq | tail -3 || true
  fi
done

if [ ! -f "$INDEX/manifest.json" ]; then
  echo "fetching the index (~270 MB) ..."
  mkdir -p "$(dirname "$INDEX")"
  curl -fL -o /tmp/kobold-index.tar.gz "$KOBOLD_INDEX_URL"
  tar -xzf /tmp/kobold-index.tar.gz -C "$(dirname "$INDEX")"
  rm -f /tmp/kobold-index.tar.gz
fi

exec python -m kleverkobold --index "$INDEX" --ollama "$OLLAMA" \
  serve --host 0.0.0.0 --port "${PF2E_PORT:-8765}"
