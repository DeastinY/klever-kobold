# pf2etune

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Runs offline](https://img.shields.io/badge/runs-fully%20offline-2f6b4f)
![No torch](https://img.shields.io/badge/runtime%20deps-4-2f6b4f)
![Memory](https://img.shields.io/badge/RAM-6.7%20GB-informational)
![Model](https://img.shields.io/badge/model-Qwen3.5--9B%20Q4-8a1b2e)
![Corpus](https://img.shields.io/badge/corpus-41%2C743%20AoN%20entries-8a1b2e)
![Benchmark](https://img.shields.io/badge/hand--written%20lookups-89.9%25-2f6b4f)
![Real questions](https://img.shields.io/badge/real%20questions-31.8%25-8a5a12)
![License](https://img.shields.io/badge/content-ORC%20%2F%20Paizo%20CUP-lightgrey)

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

## How it works

Players describe situations; a rules database holds entities, and the two share
almost no vocabulary. "An ogre has grabbed my monk" originally retrieved the
`Escape` action **7.7%** of the time. The pipeline exists to close that gap.

```
question
   │
   ├─▶ 1. Rewrite ─────── the model writes the one-line summary the answering
   │                      entry would have, plus up to 3 likely entry kinds
   │
   ├─▶ 2. Retrieve ────── seven rankings fused by reciprocal rank:
   │                      BM25 · dense(full) · dense(summary)
   │                      × {whole corpus, narrowed to those kinds}
   │                      + dense(hypothetical summary) against the summary index
   │
   ├─▶ 3. Hop ─────────── pre-Remaster entries replaced by what superseded them
   │
   ├─▶ 4. Rerank ──────── the same model picks 8 of 24 candidates listwise
   │
   └─▶ 5. Answer ─────── excerpts are authoritative; cite the URL; say so when
                          the answer is not among them
```

**Techniques, and why each is there.**

| | what it is | worth |
| --- | --- | --- |
| **Entity chunking** | one chunk per game object, never token windows | metadata filters become possible |
| **Hybrid retrieval** | BM25 + dense, fused by reciprocal rank | names and descriptions fail differently |
| **Summary index** | a second embedding over name + one-line summary | +12.4 R@5 |
| **HyDE, narrowed** | generate the *summary* an answer would have, not its name | +4.4 R@5 |
| **Kind routing** | rewriter names entry kinds; search both narrowed and not, fused | +12.4 R@5 |
| **Remaster hop** | legacy entries rewritten to their replacements | legacy questions 71% → 100% |
| **Listwise rerank** | the answering model reorders 24 → 8 | +9.4 R@8 on real questions |
| **Canonical collapse** | duplicate entries merged *before* fusion | evidence stops splitting |
| **Compact BM25** | flat inverted index in numpy | 36 MB pickle → 8 MB, no dependency |
| **float16 + mmap, blocked scoring** | index loads in 0.25 s | 583 MB → 395 MB resident |

Everything heavy is delegated to Ollama over HTTP, so the package itself needs
only `httpx`, `numpy` and `orjson` — no torch, no transformers, no CUDA.

## What we tried

Twenty-odd experiments, roughly half of which failed. The failures produced more
durable knowledge than the wins, so they are listed too. Full record with numbers
and diagnoses in [`notes/experiments.md`](notes/experiments.md).

**Shipped**

| | result |
| --- | --- |
| Retrieval over closed-book | 18% → 89.5% on the generated benchmark. The whole project in one line. |
| Query understanding (summary index, HyDE, kind routing) | recall@5 on real phrasing 47.2% → 76.4%; situational questions 7.7% → 77.4% |
| Fused narrowed + unnarrowed search | R@8 +1.1 on the gate, +17.7 on validated real questions |
| Listwise reranking | +9.4 R@8 on real questions; false-premise questions to 19/19 |
| 8 excerpts rather than 5 | 81.7% → 85.3% end to end; 12 excerpts is worse again |

**Rejected**

| | result |
| --- | --- |
| **RAFT LoRA** | **+10.1** on the generated benchmark, **−3.0** on hand-written. It learned a question shape, not the domain. |
| Abstention adapter | abandoned mid-build: the weakness it targeted was 73.7% measured and 94.7% real |
| Embedder fine-tune v1 | −12.3 R@8. Positives contained the anchor verbatim, so it learned separation without alignment |
| Embedder fine-tune v2 | recall *up* on the gate, end-to-end **down** 87.2% → 84.4% |
| One-hop link expansion | parity on the gate, −4.7 on judged answerability. A rules page cites its whole neighbourhood |
| Never excluding the `rules` category | +9 on real questions, −4.5 on the gate |

**Comparisons**

| model, with the same retrieval | generated benchmark |
| --- | ---: |
| Qwen3.5-9B (shipped, on a laptop) | **89.5%** |
| gpt-5 | 88.0% |
| Qwen3.8-27B | 85.2% |
| gpt-4.1-mini | 82.4% |
| best closed-book, any model (gpt-6-astra) | 32.5% |

Retrieval, not scale, is what closed the gap. Closed-book, everything scores
18–32%.

## Shortcomings

Stated plainly, worst first.

1. **Rule interactions are unreliable and confidently wrong.** The failure quoted
   at the top of this file cited two real pages while importing a Pathfinder 1e
   rule. This is the single largest gap and it is where a table most wants help.
2. **Real questions are much harder than the benchmark suggests.** 89.9% on
   hand-written lookups; 31.8% of retrieved excerpt sets judged to contain the
   answer on questions mined from RPG StackExchange.
3. **Lore is not indexed.** 22,604 PathfinderWiki chunks are built and unused, so
   Golarion questions are answered from Archives of Nethys article fragments.
4. **No conversation.** Every question is independent; "what about if she's
   prone?" starts from nothing.
5. **The benchmark is small and partly self-authored.** 109 hand-written items
   means one item is 0.9%, and the author's blind spots are in it by
   construction — the mined set exists because of that and is itself only 85
   validated items.
6. **The generated benchmark flatters everything.** It names its target entity in
   88% of questions. Kept for continuity; it decides nothing.
7. **No auth on the web UI.** `--host 0.0.0.0` is documented for reaching it from
   a tablet; do not expose it beyond a home network.
8. **Structured queries go through semantic search.** "Level 4 fighter feats with
   the flourish trait" is a `WHERE` clause wearing a question's clothes.

## Future work

Ordered by where the errors actually are, not by what is interesting to build.

**Retrieval — two thirds of remaining gate failures**

- A cross-encoder reranker over a wider pool. The current reranker is the
  answering model, chosen to avoid a torch dependency; a real one would be better
  if the deployment can afford it.
- Multi-hop along a *reasoned* path. A blanket one-hop walk failed; asking the
  model which link to follow has not been tried.
- Embedder fine-tuning on **teacher-written player questions** with mined hard
  negatives. Two cheaper variants failed for diagnosed reasons; this is the
  version the evidence still supports.
- A structured query path for filterable questions, bypassing embeddings.

**Coverage**

- Index the lore with a source filter so it never answers a rules question.
- Monthly re-dump for errata, gated on the holdout before publishing.

**Product**

- Multi-turn follow-ups — the largest gap between this and something usable.
- Character context: import a Pathbuilder JSON, filter to what *this* character
  can take.
- A Foundry VTT module. `foundryvtt/pf2e` is Apache-2.0 and Paizo-partnered.
- Streaming output; 1.6 s to first token feels slower than it is.

**Measurement**

- Grow the holdout past 300 and split dev from test. Everything so far has been
  tuned on the set it is reported on.
- Mine questions from more sources; one forum is one community's blind spots.
- Cross-check the grader against a judge on a sample and read every
  disagreement — that is how bug sixteen gets found.

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

## Contributing

[`CONTRIBUTING.md`](CONTRIBUTING.md) — mostly the measurement discipline, which is
the part of this project worth copying. Short version: the gate is 109
hand-written questions, run it before and after, record the number when your
change loses, and treat an implausible number as a bug until proven otherwise.

## Licensing

Rules mechanics are ORC-licensed; Golarion lore and PathfinderWiki are under
Paizo's Community Use Policy — non-commercial, freely available use only. See
[`docs/LICENSING.md`](docs/LICENSING.md). This repository is for personal,
non-commercial research.
