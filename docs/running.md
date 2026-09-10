# Running it

## The short version

```bash
uv tool install git+https://github.com/DeastinY/klever-kobold
kobold setup --install-ollama     # Ollama if missing, both models, the index
kobold serve                      # http://localhost:8765
```

The one-line installers in the README do exactly this, plus installing
[uv](https://docs.astral.sh/uv/) itself and opening the browser:
[`deploy/install.sh`](../deploy/install.sh) for macOS and Linux,
[`deploy/install.ps1`](../deploy/install.ps1) for Windows. Both are safe to re-run.

`kobold setup` is idempotent. Without `--install-ollama` it prints the Ollama
install command for your platform and stops; with it, it runs Homebrew on macOS,
the official script on Linux, and winget on Windows. Either way it starts the
Ollama server if it is installed but not running, which is the step people miss.
`kobold doctor` checks each part separately when something breaks.

## What gets installed where

| | |
| --- | --- |
| Ollama | its own installer; models under `~/.ollama` |
| Models | `qwen3.5:4b` (3.4 GB) answers, `qwen3-embedding:0.6b` (0.6 GB) retrieves; `qwen3.5:9b` (6.6 GB) is pulled the first time you choose **Better** |
| The index | 270 MB download, 460 MB unpacked, under `~/Library/Application Support/kleverkobold` on macOS, `~/.local/share/kleverkobold` on Linux, `%LOCALAPPDATA%\kleverkobold` on Windows; `--index` or `KOBOLD_INDEX` override it |
| The program | four pure-Python dependencies, no torch |

Memory while answering: about 5.6 GB with the default model, 8.8 GB with the 9B.
A 16 GB laptop is comfortable with the 4B and sluggish with the 9B.

## Choosing the model

The 4B answers by default: 93/109 on the hand-written holdout against the 9B's
100, at twice the speed and half the memory. `--llm-model qwen3.5:9b` runs the
9B from the command line; in the web UI it is the **Better** preset under
Settings, and the first choice is made on the onboarding card. Below 4B the
models start answering Pathfinder questions with D&D 5e rules.

Any OpenAI-compatible server can do the answering instead — LM Studio,
llama.cpp, vLLM, a hosted API — via Settings → Expert mode, or
`--backend openai --ollama http://host:port/v1 --llm-model name`. Retrieval
keeps this server's own embedder unless you say otherwise, because querying the
index with a different encoder returns plausible, unrelated entries.

## The web UI

- **Enter** asks; **Shift+Enter** shows only the entries; **↑** brings back
  earlier questions; **/** focuses the box; **?** reopens the onboarding card.
- Entries open in a popout; **←** and **→** step through them; **Esc** closes.
- **★** on any entry keeps it on the front page. History is under the History
  button; both live in your browser only.
- **Settings** has the two presets, **What it digs through** (rules only; rules
  and Golarion lore when the question is about the world, the default; or both
  every time), and an **Expert mode** switch for the model server, retrieval
  knobs (excerpts, rerank, context length, answer length), the embedder, and
  the MCP snippets. The per-stage timing under each answer appears in expert
  mode too.
- **Wrong? Report it** under every answer: see [reporting.md](reporting.md).
- **Follow-up questions** is in Expert mode, under Conversation, and is **off**.
  Turned on, the kobold reads your last question and its answer, rewrites a
  follow-up like "what if she's prone?" into a question that can be looked up,
  and searches the Archives again for what it now understands you to be asking.
  It shows you that rewritten question, because when a follow-up goes wrong
  that line is almost always where. Only the last turn travels; a line above
  the box says which one, with a way to start fresh. Costs one extra model
  call, roughly a sixth of an answer — see
  [notes/followup-design.md](../notes/followup-design.md).

`kobold serve --host 0.0.0.0` makes it reachable from a phone or tablet on your
network. There is no login; do not expose it to the internet.

## The command line

```bash
kobold ask "an ogre grabbed my monk, what can she do?"   # streams an answer with sources
kobold ask "who rules Cheliax?"                           # lore, from PathfinderWiki
kobold search "grabbed"                                   # what retrieval finds, no answer
kobold search --scope lore "Desna"                        # the deity's stat block and her wiki page
kobold chat                                               # a conversation; follow-ups work
kobold doctor                                             # Ollama, models, index
```

`ask` is one shot and every question is independent. `chat` keeps one turn, so
"and what if she's prone?" means something; `/new` forgets the thread and
ctrl-d stops. `--timings` shows what the extra stage cost.

Global flags go before the subcommand: `--index`, `--ollama`, `--backend`,
`--llm-model`, `--embed-model`. `ask` and `search` take `--scope rules|lore|auto`
(default `auto`: the kobold decides per question, and a rules question never
sees lore). `serve` adds `--host`, `--port`, `--context-chars` and `--report-url`.

## Claude Desktop and Claude Code

`kobold mcp` is a stdio MCP server with two tools: `kobold_ask` runs the whole
pipeline; `kobold_search` returns the entries for the calling model to read
itself, which is the better choice when the caller is a strong model.

Claude Desktop, in its MCP configuration:

```json
{ "mcpServers": { "kobold": { "command": "kobold", "args": ["mcp"] } } }
```

Claude Code:

```bash
claude mcp add kobold -- kobold mcp
```

If `kobold` is not on the PATH for those apps, use the interpreter that has it:
`"command": "/path/to/.venv/bin/python", "args": ["-m", "kleverkobold", "mcp"]`.
Web UI settings do not travel to the MCP server; it takes the same command-line flags.

## Docker

For Linux and Windows, `docker compose up` runs Ollama and the kobold together;
see [`deploy/README.md`](../deploy/README.md). Not on Apple Silicon: a container
cannot reach Metal, so Ollama would run on the CPU at a fraction of the speed.
On a Mac use the installer or uv.

## Updating and removing

```bash
uv tool upgrade kleverkobold      # the program
kobold setup                      # picks up a new index release if one is out
uv tool uninstall kleverkobold    # the program; models stay with Ollama, the index in the data directory
```

## Building from a clone

```bash
git clone https://github.com/DeastinY/klever-kobold && cd klever-kobold
uv sync && uv run kobold serve
```

## Rebuilding the index

Needs a GPU for the two embedding passes and the build extras:

```bash
uv sync --extra corpus --extra retrieval --extra local
uv run scripts/rebuild_index.sh          # dump -> chunks -> embed -> package, with checks
```

Output lands in `dist/kobold-index`. Run the test set on it (see
[CONTRIBUTING.md](../CONTRIBUTING.md)), then publish:

```bash
tar czf kobold-index.tar.gz -C dist kobold-index
gh release create index-vN kobold-index.tar.gz --title "Packaged index vN"
```

and point `INDEX_URL` in `src/kleverkobold/app.py` at the new tag. `kobold setup`
everywhere then fetches it. The build scripts read the Archives of Nethys and
PathfinderWiki: run them rarely, and never in a loop.
