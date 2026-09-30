# Running it

## The short version

```bash
uv tool install --python 3.13 git+https://github.com/DeastinY/klever-kobold
kobold setup --install-ollama     # Ollama if missing, both models, the index
kobold serve                      # opens http://localhost:8765 in your browser
```

The one-line installers in the README do exactly this, plus installing
[uv](https://docs.astral.sh/uv/) itself:
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

`kobold serve` opens the page in your browser as soon as it is listening;
`--no-browser` (or `KOBOLD_NO_BROWSER=1`) leaves that to you, which is what a
headless machine or a service unit wants.

`kobold serve --host 0.0.0.0` makes it reachable from a phone or tablet on your
network, and the settings panel then shows the address as a QR code to scan.
There is no login; do not expose it to the internet.

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

## The Windows installer

`KleverKoboldSetup.exe` on the [latest release](https://github.com/DeastinY/klever-kobold/releases/latest)
is the same program frozen with PyInstaller and wrapped by Inno Setup, for
people who would rather not open a terminal. It is per-user, like Ollama's own
installer: no administrator rights, no UAC prompt.

What it does, in order:

1. Copies the program to `%LOCALAPPDATA%\Programs\KleverKobold` and, if you
   leave the box ticked, adds it to your PATH so `kobold` works in a terminal
   and in Claude Desktop's MCP config.
2. If Ollama is not installed, downloads `OllamaSetup.exe` from ollama.com
   (about 1.5 GB) and runs it silently. An Ollama already on the machine is
   left alone.
3. Offers to run `kobold setup` (the two models, about 4 GB, and the index,
   270 MB) and to open the kobold. Both are Start menu entries as well, next to
   *Kobold doctor*.

It is not code-signed, so SmartScreen shows "Windows protected your PC" the
first time: *More info*, then *Run anyway*. Everything else is as with the
script install: same data directory, same `kobold` command, same page.

**Updating**: the page still says when a newer kobold is out, but instead of an
Upgrade button it links to the release; download the new installer and run it
over the old one. **Removing**: *Settings → Apps → The Klever Kobold*. Ollama,
its models, and the index stay; remove those separately if you want the disk back.

**Building it**: the *Windows installer* workflow under Actions builds it on a
Windows runner from any commit (a `v*` tag attaches it to that release), then
installs it on that runner silently, checks that Ollama landed alongside and
`kobold` is on the PATH, and uninstalls it again; a pull request touching the
installer runs the same. Tick *end_to_end* to also pull the models and run
`kobold doctor` there. The pieces are in [`deploy/windows/`](../deploy/windows/): `kobold.spec` (the
freeze), `kobold.iss` (the installer), `launcher.py` (the frozen entry point).
Tick *bundle_ollama* to embed `OllamaSetup.exe` in the installer for machines
that cannot download it during install; that makes it about 1.6 GB.

## Docker

For Linux and Windows, `docker compose up` runs Ollama and the kobold together;
see [`deploy/README.md`](../deploy/README.md). Not on Apple Silicon: a container
cannot reach Metal, so Ollama would run on the CPU at a fraction of the speed.
On a Mac use the installer or uv.

## Updating and removing

```bash
kobold upgrade                    # the program, if a newer one is out (or the page's Upgrade button)
uv tool upgrade kleverkobold      # the same, by hand
kobold setup                      # picks up a new index release if one is out
uv tool uninstall kleverkobold    # the program; models stay with Ollama, the index in the data directory
```

Installed with `KleverKoboldSetup.exe` instead: run the newer installer over
the old one, and remove it from *Settings → Apps*.

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
