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
    KOBOLD_INDEX=/data/kobold-index \
    OLLAMA_URL=http://ollama:11434 \
    KOBOLD_INDEX_URL=https://github.com/DeastinY/klever-kobold/releases/download/index-v1/kobold-index.tar.gz

EXPOSE 8765
# No browser in a container; the address is printed instead.
ENV KOBOLD_NO_BROWSER=1
ENTRYPOINT ["deploy/entrypoint.sh"]
