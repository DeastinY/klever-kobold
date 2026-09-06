# Running on a MacBook

The whole runtime is four pure-Python dependencies and about 250 MB of index.
Ollama does the model work; nothing here needs torch, transformers, or a GPU.

## Memory budget on a 16 GB machine

| | |
| --- | ---: |
| `qwen3.5:9b` (Q4, held by Ollama) | 5.7 GB |
| `qwen3-embedding:0.6b` | 0.6 GB |
| index (memory-mapped, mostly page cache) | 0.25 GB |
| Python runtime | 0.06 GB |
| **total** | **~6.6 GB** |

Leaves comfortable room for macOS and a browser. Ollama unloads models after five
minutes idle, so the steady-state cost is lower still.

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

# 4. The index — build it once (needs ~15 min and network), or copy dist/pf2e-index across
.venv/bin/python scripts/dump_aon.py
.venv/bin/python scripts/build_chunks.py
.venv/bin/python scripts/package_index.py     # requires the dev extras to embed; see below

# 5. Check
PYTHONPATH=src .venv/bin/python -m pf2etune doctor
```

Building the index from scratch needs an embedding model, which means the heavier
`[retrieval]` extra. **Copying `dist/pf2e-index/` from another machine avoids that
entirely** and is the recommended path — the index is portable, and the runtime
reproduces its query embeddings through Ollama (verified: cosine 0.999 against the
embeddings the index was built with).

## Use

```bash
export PYTHONPATH=src

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

## What to expect

On hand-written questions phrased the way players actually ask, retrieval finds
the right entry 72.9% of the time in the top 5, and end-to-end answers score
around 82%. Questions that name a feat or spell outright do far better than
situational ones. Every answer cites its Archives of Nethys URL; when the
excerpts do not contain the answer the model is instructed to say so, and mostly
does.

## If something breaks

`doctor` checks each part separately and names the failure. The three common ones:

- **"Cannot reach Ollama"** — `ollama serve` is not running.
- **"Ollama does not have the model"** — the `ollama pull` steps were skipped.
- **"No index at ..."** — `dist/pf2e-index/` is missing; copy it or build it.
