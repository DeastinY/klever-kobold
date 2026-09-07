# pf2etune

A Pathfinder 2e rules reference that runs on your own machine, searches the
Archives of Nethys, and cites its sources.

```bash
docker compose up          # then open http://localhost:8765
```

---

## Read this before you trust it

This is a **lookup tool**, not a rules adjudicator. The distinction is not
modesty — it is measured, and it matters most exactly where you would want help.

| Ask it | How it does |
| --- | --- |
| "What level is Battle Medicine?" | **Reliable.** |
| "How does Treat Wounds work?" | **Reliable**, with a citation you can check. |
| "Is there a feat that makes falling less dangerous?" | **Mostly** — about three times in four. |
| "Was Magic Missile renamed?" | **Mostly** — about five times in six. |
| **"Does X interact with Y?"** | **Do not trust it.** |
| "Tell me about Cheliax" | **Thin.** Lore is not indexed yet. |

A real failure, verbatim, asked whether a rogue gets sneak attack on the
*fighter's* Reactive Strike:

> **Yes, she gets Sneak Attack damage.** … a creature is flat-footed if they are
> flanked by at least two enemies and have not yet acted in the current round (or
> are otherwise denied their Dexterity bonus).

That answer is wrong three times over. Sneak attack applies to the rogue's own
Strikes. *Flat-footed* is the pre-Remaster name for *off-guard*. And "denied
their Dexterity bonus" is Pathfinder 1e language for a rule 2e does not have. It
cited two real Archives of Nethys pages while doing it.

**Interaction questions are where it fails and where a table most wants an
answer.** Use it to find the rule fast; read the rule yourself before settling an
argument. Every answer carries its source URL precisely so that is a one-click
check — the web UI puts the rules entries first and the generated answer behind a
button for the same reason.

Measured: **89.9%** on 109 hand-written questions, but those are lookups. On 85
real questions mined from RPG StackExchange, only **31.8%** of retrieved excerpt
sets are judged to contain the answer outright, against 56% for the hand-written
ones. The full record, including everything that failed, is in
[`notes/experiments.md`](notes/experiments.md).

---

## Run it

**Docker** — one command, no Python setup. First run pulls ~6.3 GB of models and
a 143 MB index into named volumes; later runs start in seconds. Works on CPU;
uncomment the GPU block in `docker-compose.yml` if you have an NVIDIA card.

```bash
docker compose up
```

**On a laptop, without Docker** — 6.7 GB resident, ~1.6 s a question, no torch
and no CUDA. See [`deploy/README.md`](deploy/README.md).

```bash
bash deploy/install.sh
PYTHONPATH=src .venv/bin/python -m pf2etune serve     # web UI
PYTHONPATH=src .venv/bin/python -m pf2etune ask "..."  # one-shot
```

**In Claude Desktop or Claude Code** — an MCP server exposing `pf2e_ask` and
`pf2e_search`. Prefer `pf2e_search` when the caller is a strong model: hand it
the rules text and let it reason, since retrieval is the part that carries this
system. Config in [`deploy/README.md`](deploy/README.md).

---

## What it does

Players describe situations; a rules database holds entities, and the two share
almost no vocabulary. "An ogre has grabbed my monk" originally retrieved the
`Escape` action **7.7%** of the time. So the model goes in front of the retriever
as well as behind it:

1. **Rewrite** — the question becomes a hypothetical one-line entry summary plus
   up to three likely entry kinds. Asking for a *description* rather than a *name*
   matters: asked to name things, the model invents feats that do not exist.
2. **Narrow** — restrict to those kinds. Equipment and creatures are two thirds of
   the corpus and answer almost none of these questions.
3. **Retrieve** — fuse four rankings by reciprocal rank: BM25, dense over the full
   entry, dense over the one-line summary, and the *hypothetical* summary against
   the summary index.
4. **Hop** — replace any pre-Remaster entry with the one that superseded it, so
   legacy rules are never served as current.
5. **Answer** — excerpts are authoritative; cite the URL; say so when the answer
   is not among them.

Retrieval on hand-written questions went from 47.2% to **76.4%** recall@5 this way,
and situational questions from 7.7% to **77.4%**.

## Results

| | hand-written | generated |
| --- | ---: | ---: |
| Deployed runtime (Ollama, k=8) | **85.3%** | — |
| Lab path (transformers, nf4) | 84.4% | 84.5% |
| With the RAFT LoRA | 81.7% | 94.6% |
| gpt-5 + retrieval | — | 83.7% |
| Best closed-book (gpt-6-astra) | — | 31.6% |

**The two columns disagreeing is the main finding.** The generated benchmark names
its target entity in 88% of questions; the hand-written one, 37%. A fine-tune
worth +10 points on the first is worth −3 on the second. Numbers from a benchmark
written by the same pipeline that produced the training data describe the
pipeline, not the world.

Full history in [`notes/experiments.md`](notes/experiments.md), including
everything that was tried and dropped.

## Layout

```
src/pf2etune/    app.py (runtime) · retrieval.py · bm25.py · mcp_server.py · __main__.py
                 aon.py · wiki.py · normalize.py (corpus build)
scripts/         corpus pipeline, index build, packaging, query rewriting, LoRA training
eval/            two benchmarks, deterministic scorer, 25 pinned regression tests
deploy/          MacBook install, requirements, install.sh
notes/           research, prior art, experiment log, roadmap
docs/            the dossier, licensing
```

## Corpus

| Source | Chunks | Tokens | License |
| --- | ---: | ---: | --- |
| [Archives of Nethys](https://2e.aonprd.com/) | 41,743 | 13.5 M | ORC / Paizo CUP |
| [PathfinderWiki](https://pathfinderwiki.com/) | 22,604 | 5.6 M | Paizo CUP |

Rebuilt from scratch by four scripts; nothing derived is committed. The packaged
retrieval index ships as a [release asset](https://github.com/DeastinY/pf2etune/releases).

## A note on the scorer

Ten measurement bugs were found over this project's life, every one by reading
model outputs rather than model scores, and the largest ran in the flattering
direction for hours. `eval/test_score.py` pins 25 cases taken verbatim from real
runs. If you change the grader, run it.

## Licensing

Rules mechanics are ORC-licensed; Golarion lore and PathfinderWiki are under
Paizo's Community Use Policy — non-commercial, freely available use only. See
[`docs/LICENSING.md`](docs/LICENSING.md). This repository is for personal,
non-commercial research.
