# Running on a MacBook

The whole runtime is four pure-Python dependencies and about 250 MB of index.
Ollama does the model work; nothing here needs torch, transformers, or a GPU.

## Memory budget on a 16 GB machine

| | |
| --- | ---: |
| `qwen3.5:9b` (Q4, held by Ollama) | 5.7 GB |
| `qwen3-embedding:0.6b` | 0.6 GB |
| Python process, peak (measured) | 0.4 GB |
| **total** | **~6.7 GB** |

Leaves comfortable room for macOS and a browser. Ollama unloads models after five
minutes idle, so the steady-state cost is lower still.

The Python side is measured, not estimated: 395 MB peak resident, of which about
110 MB is entry metadata and 50 MB the BM25 index. Embeddings are memory-mapped
and scored in blocks, so the 170 MB float32 upcast a naive matrix multiply would
allocate never happens; entry text is read from disk by byte offset for the eight
entries an answer actually quotes. Index loads in 0.25 s, a search takes 0.45 s,
a full answer about 1.6 s.

## Install

```bash
# 1. Ollama, if you do not have it
brew install ollama
ollama serve &            # or launch Ollama.app

# 2. Models
ollama pull qwen3.5:9b
ollama pull qwen3-embedding:0.6b

# 3. This package
git clone git@github.com:DeastinY/pf2etune.git
cd pf2etune
python3 -m venv .venv && .venv/bin/pip install -r deploy/requirements.txt

# 4. The index (143 MB download, 244 MB unpacked)
gh release download index-v1 --pattern 'pf2e-index.tar.gz'
mkdir -p dist && tar -xzf pf2e-index.tar.gz -C dist

# 5. Check
PYTHONPATH=src .venv/bin/python -m pf2etune doctor
```

The index is a release asset rather than a repo file, and downloading it is the
recommended path: building one from scratch needs an embedding model and so the
much heavier `[retrieval]` extra. The prebuilt index is portable because the
runtime reproduces its query embeddings through Ollama — verified at cosine 0.999
against the embeddings the index was actually built with.

Or, without the `gh` CLI:

```bash
curl -L -o pf2e-index.tar.gz \
  https://github.com/DeastinY/pf2etune/releases/download/index-v1/pf2e-index.tar.gz
mkdir -p dist && tar -xzf pf2e-index.tar.gz -C dist
```

## Use

```bash
export PYTHONPATH=src

# web UI for the table — rules entries first, generated answer behind a button
.venv/bin/python -m pf2etune serve
# ...then http://localhost:8765, or --host 0.0.0.0 to reach it from a tablet

# ask a question
.venv/bin/python -m pf2etune ask "an ogre grabbed my monk, what can she do?"

# see what retrieval finds, without spending tokens on an answer
.venv/bin/python -m pf2etune search "a feat that makes falling less dangerous"

# check every moving part
.venv/bin/python -m pf2etune doctor
```

## As an MCP server

Claude Desktop — `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pf2e": {
      "command": "/absolute/path/to/pf2etune/.venv/bin/python",
      "args": ["-m", "pf2etune", "mcp"],
      "env": { "PYTHONPATH": "/absolute/path/to/pf2etune/src" }
    }
  }
}
```

Claude Code: `claude mcp add pf2e -- /absolute/path/to/.venv/bin/python -m pf2etune mcp`

Two tools are exposed. `pf2e_ask` runs the whole pipeline locally. **`pf2e_search`
returns the rules excerpts and lets the calling model reason over them** — worth
preferring when the caller is a frontier model, since retrieval is the part that
carries this system and a stronger reader does better with the same excerpts.

## Docker instead

**On this machine, containerise the app but not Ollama.**

```bash
ollama serve &                                 # or Ollama.app
docker compose -f docker-compose.mac.yml up
```

Docker Desktop runs containers inside a Linux VM and that VM cannot reach Metal —
Apple's Hypervisor.framework does not pass the GPU through — so an Ollama
container on Apple Silicon falls back to CPU and runs 2–5x slower. Keeping Ollama
native costs nothing: it holds every heavy thing, and this app is four
pure-Python dependencies.

Honestly, on a Mac `deploy/install.sh` is simpler still and gives the same
performance. Docker is worth it here mainly if you want the service supervised
and restarting on its own.

(`docker compose up`, with the plain file, brings up Ollama as a second container.
That is the right shape on Linux with an NVIDIA card and the wrong one here.)

## What to expect

Measured on 109 hand-written questions phrased the way players actually ask —
describing a feat rather than naming it, asking what to do in a situation, using
pre-Remaster vocabulary, asking about things that do not exist:

| | |
| --- | ---: |
| **overall** | **85.3%** |
| situational ("an ogre grabbed my monk") | 100% |
| comparative ("Shove or Trip?") | 100% |
| pre-Remaster vocabulary | 85.7% |
| false premise ("how does attunement work?") | 73.7% |
| descriptive ("a feat that makes falling less dangerous") | 72.7% |
| retrieval recall@5 | 76.4% |

The weak spot is questions about things that do not exist: it still invents an
answer roughly one time in five. Every answer cites its Archives of Nethys URL,
so a wrong one is usually obvious from a wrong-looking citation.

## If something breaks

`doctor` checks each part separately and names the failure. The three common ones:

- **"Cannot reach Ollama"** — `ollama serve` is not running.
- **"Ollama does not have the model"** — the `ollama pull` steps were skipped.
- **"No index at ..."** — `dist/pf2e-index/` is missing; copy it or build it.
