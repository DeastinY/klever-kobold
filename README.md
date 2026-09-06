# pf2etune

Adapting an open-weight LLM to **Pathfinder 2e** rules and lore.

The premise, from the research writeup in [`notes/research.md`](notes/research.md)
(prior art with links: [`notes/prior-art.md`](notes/prior-art.md)): a general
model's PF2e failures are two different problems with two different fixes.

| Failure | Fix |
| --- | --- |
| Doesn't know a feat's exact level, traits, or damage scaling | **Retrieval.** 41k discrete entities with exact numbers is a lookup problem. |
| Answers with bonus actions, death saves, and advantage | **Fine-tuning.** That's a corrupted D&D 5e prior, not a missing fact. |

Retrieval fixes facts; fine-tuning fixes priors. PF2e gives you both problems, which is why the
handful of [existing hobby PF2e RAG bots](notes/prior-art.md) underdeliver — they hand correct chunks to a model that
still thinks in 5e. The plan is a retrieval-first stack plus a small LoRA that kills the 5e prior,
enforces Remaster vocabulary, and teaches grounded citation and abstention.

**Baseline model: `Qwen/Qwen3.8-27B`** (Apache-2.0, 27.8B dense, 262k context) — QLoRA-trainable on
the target 32 GB RTX 5090.

## Corpus

Both sources are rebuilt from scratch by the scripts below; nothing derived is committed.

| Source | Documents | ~Tokens | Content | License |
| --- | ---: | ---: | --- | --- |
| [Archives of Nethys](https://2e.aonprd.com/) | 41,743 | 13.5 M | Rules, feats, spells, creatures, equipment | ORC / Paizo CUP |
| [PathfinderWiki](https://pathfinderwiki.com/) | 22,604 | 5.6 M | Golarion lore, people, places, organizations | Paizo CUP |

AoN serves its search index from an anonymously readable Elasticsearch cluster with a
pre-rendered `markdown` field per entity — the cleanest PF2e rules text available anywhere.
Normalisation keeps the metadata that makes filtered retrieval work (level, traits, rarity, source
book, Remaster status) and the **403k outbound entity links**, which are the natural seed for
EntiGraph-style synthetic continued pretraining later.

The Remaster split is preserved and is load-bearing: 12,400 Remaster entries, 11,876 superseded
legacy entries, 17,467 unaffected. Pre-2023 web text — which is what every base model was trained
on — uses the legacy names.

## Benchmark

No public PF2e rules benchmark exists, so `eval/generate_benchmark.py` builds one where every
answer is checkable against a structured field rather than a model's opinion. 470 items:

| Family | Items | Probes |
| --- | ---: | --- |
| `lookup_level` | 80 | Exact attribute recall |
| `lookup_traits` | 80 | Complete set recall |
| `lookup_rarity` | 80 | Non-majority-class recall |
| `prereq` | 80 | Multi-hop feat prerequisites |
| `remaster_rename` | 80 | Legacy-name staleness |
| `abstention` | 40 | Inventing feats that don't exist |
| `trap_5e` | 30 | **D&D 5e contamination** (hand-authored) |

The `trap_5e` family is the important one. Each item carries `must_not_contain` — the 5e vocabulary
that must never appear ("bonus action", "death saving throw", "advantage") — which makes 5e
contamination automatically scoreable.

## Build the corpus

```bash
uv venv && uv pip install -e .

python scripts/dump_aon.py          # ~45.5k docs from the AoN Elasticsearch index
python scripts/dump_wiki.py         # ~27.8k pages from the PathfinderWiki API (~10 min, rate-limited)
python scripts/build_chunks.py      # AoN  -> data/processed/aon_chunks.jsonl
python scripts/build_wiki_chunks.py # wiki -> data/processed/wiki_chunks.jsonl
python scripts/corpus_stats.py      # -> data/processed/corpus_stats.json
python eval/generate_benchmark.py   # -> eval/benchmark.jsonl
```

## Layout

```
src/pf2etune/     aon.py (ES export) · wiki.py (MediaWiki export) · normalize.py (chunking)
scripts/          corpus build pipeline
eval/             benchmark generator + hand-authored 5e-trap seeds
docs/             research writeup as a web page, licensing notes
notes/            research findings, decisions
data/             raw + processed corpora (gitignored; rebuild from scripts)
```

## Licensing

Rules mechanics are ORC-licensed; Golarion lore and PathfinderWiki are under Paizo's Community
Use Policy — **non-commercial, freely available use only**. See [`docs/LICENSING.md`](docs/LICENSING.md).
Every chunk keeps its source URL so attribution stays possible. This repository is for personal,
non-commercial research.
