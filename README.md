# pf2etune

A Pathfinder 2e rules assistant that runs on a laptop, answers questions the way
players actually ask them, and cites Archives of Nethys for every answer.

**85.3%** on 109 hand-written questions, running locally through Ollama at about
1.6 seconds a question and 6.6 GB of memory. → **[deploy/README.md](deploy/README.md)**

```bash
$ pf2etune ask "my monk is grabbed by an ogre, what are her options?"

Escape (one action, attack trait): attempt an unarmed attack, Athletics or
Acrobatics check against the ogre's DC. Success removes the grabbed condition.
While grabbed she is off-guard and immobilized, and any manipulate action
requires a DC 5 flat check.

sources:
  Escape (action) — https://2e.aonprd.com/Actions.aspx?ID=2412
  Grabbed (condition) — https://2e.aonprd.com/Conditions.aspx?ID=19
```

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
