# The runtime is four pure-Python dependencies, so this stays small and needs no
# build toolchain, no CUDA and no model weights. Ollama runs as its own service
# and holds the models; see docker-compose.yml.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY deploy/requirements.txt deploy/requirements.txt
RUN pip install --no-cache-dir -r deploy/requirements.txt

COPY src/ src/
COPY deploy/entrypoint.sh deploy/entrypoint.sh
RUN chmod +x deploy/entrypoint.sh

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PF2E_INDEX=/data/pf2e-index \
    OLLAMA_URL=http://ollama:11434 \
    PF2E_INDEX_URL=https://github.com/DeastinY/pf2etune/releases/download/index-v1/pf2e-index.tar.gz

EXPOSE 8765
ENTRYPOINT ["deploy/entrypoint.sh"]
