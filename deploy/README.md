# Running on a MacBook

The whole runtime is four pure-Python dependencies and about 460 MB of index.
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
uv tool install git+ssh://git@github.com/DeastinY/klever-kobold
kobold setup --install-ollama                  # Ollama, both models, the index
kobold doctor                                  # verify each part
```

`--install-ollama` runs `brew install ollama` for you. Leave it off and setup
prints the command and stops without touching anything — if you would rather do
it yourself, that is `brew install ollama`, or the app from
[ollama.com/download](https://ollama.com/download). Either way setup starts the
server if it is installed but not running, which is the step people miss.

That is the whole thing. The index goes to
`~/Library/Application Support/kleverkobold/kobold-index` and survives tool upgrades.

Without uv, from a clone:

```bash
git clone git@github.com:DeastinY/klever-kobold.git && cd kleverkobold
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/kobold setup
```

## Use

```bash
export PYTHONPATH=src

# web UI for the table — rules entries first, generated answer behind a button
.venv/bin/python -m kleverkobold serve
# ...then http://localhost:8765, or --host 0.0.0.0 to reach it from a tablet

# ask a question
.venv/bin/python -m kleverkobold ask "an ogre grabbed my monk, what can she do?"

# see what retrieval finds, without spending tokens on an answer
.venv/bin/python -m kleverkobold search "a feat that makes falling less dangerous"

# check every moving part
.venv/bin/python -m kleverkobold doctor
```

## As an MCP server

Claude Desktop — `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kobold": {
      "command": "/absolute/path/to/kleverkobold/.venv/bin/python",
      "args": ["-m", "kleverkobold", "mcp"],
      "env": { "PYTHONPATH": "/absolute/path/to/kleverkobold/src" }
    }
  }
}
```

Claude Code: `claude mcp add kobold -- /absolute/path/to/.venv/bin/python -m kleverkobold mcp`

Two tools are exposed. `kobold_ask` runs the whole pipeline locally. **`kobold_search`
returns the rules excerpts and lets the calling model reason over them** — worth
preferring when the caller is a frontier model, since retrieval is the part that
carries this system and a stronger reader does better with the same excerpts.

## Docker on a Mac — usually don't

Docker Desktop runs containers inside a Linux VM that cannot reach Metal, so a
containerised Ollama on Apple Silicon falls back to CPU and runs 2–5x slower.
uv above is both simpler and faster.

If you want the app supervised and restarting on its own, keep Ollama native and
containerise only the app:

```bash
ollama serve &
docker compose -f docker-compose.mac.yml up
```

## MLX on Apple Silicon

**You probably already have it.** Ollama replaced its llama.cpp Metal backend
with Apple's MLX in 0.19, which roughly doubled decode speed on M-series
hardware. `kobold doctor` reports your Ollama version and says which backend that
means you are on.

```bash
kobold doctor        # ...  ok  ollama version  0.33.2  — uses MLX on Apple Silicon
```

If it says you are below 0.19, `brew upgrade ollama` is the whole optimisation.

If you would rather use a different MLX server —
[mlx-serve](https://github.com/raspoli/mlx-serve),
[vllm-mlx](https://github.com/waybarrios/vllm-mlx),
[mlx-openai-server](https://github.com/cubist38/mlx-openai-server), or LM Studio —
anything speaking the OpenAI API works:

```bash
kobold --backend openai --ollama http://localhost:8080/v1 \
     --llm-model mlx-community/Qwen3.5-9B-4bit serve
```

**The embedding model is not interchangeable.** The index was built with
`Qwen3-Embedding-0.6B`, and querying it with a different encoder returns
plausible but unrelated entries rather than failing. The manifest carries a
fingerprint of the encoder that built it and startup checks against it, so a
mismatch stops with a message naming both models instead of quietly degrading.
In practice: serve the LLM wherever you like, keep the embedder on the model the
index names.

## First start

`serve` loads both models before it accepts questions and says so — in the
terminal and in the page, which shows a status line and keeps the input disabled
until it is ready. On a laptop that first load reads several gigabytes off disk
and can take a minute; afterwards models stay resident for two hours of idle
time, so a session's worth of questions costs nothing extra.

The page has an Auto / Light / Dark toggle, remembered per browser. Auto follows
the system setting.

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
- **"No index at ..."** — `dist/kobold-index/` is missing; copy it or build it.
