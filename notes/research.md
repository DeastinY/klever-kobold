# Research: adapting an LLM to Pathfinder 2e

Survey conducted 2026-09-06.

## Prior art: the field is empty

- **HuggingFace models**: zero PF2e language models. The only PF2e artifacts on the Hub are
  `Kaylebor/pf2e-codex-embed-xs` and `pf2e-codex-reranker-*` — a retrieval stack fine-tuned from
  Snowflake Arctic-Embed / MiniLM, ~93 downloads. Someone built PF2e RAG components, not a model.
- **HuggingFace datasets**: zero PF2e rules or lore corpora. `exnihilum/ttrpg-rpg-fandom-com-en` is
  a generic fandom-wiki scrape.
- **GitHub**: a handful of 0–2 star hobby RAG bots — `MahmuudIbrahim/Pathfinder-Rules-LLM`
  (Pf2ools JSON + SRD markdown → ChromaDB → Claude/GPT), `ClawedMaple/PF2e-RAG`,
  `tvanfossen/pathfinder-society-scribe`. All RAG, all thin, none evaluated.
- **Benchmarks**: no PF2e rules benchmark exists. Adjacent only: D20bench (5e combat), LudoBench,
  RPGBench.

The community's own diagnosis is the right problem statement: general models fail at PF2e not from
missing data but from **D&D 5e contamination** — 5e dominates the training distribution, so models
answer PF2e questions confidently with 5e mechanics.

## Data: unusually good

**Archives of Nethys** serves its search index from an anonymously readable Elasticsearch cluster:

```
POST https://elasticsearch.aonprd.com/aon/_search   → 45,547 documents
```

Each document has a pre-rendered `markdown` field — clean, structured, link-annotated, one document
per game entity. Anonymous access is read-only and blocks scroll/PIT, so `scripts/dump_aon.py`
paginates per category (largest is `equipment` at ~9.1k, comfortably inside the 10k window).

The corpus carries `legacy_id` / `remaster_id` cross-references, which separates Remaster from
pre-Remaster content — a second contamination axis, and the source of a free 2,019-item renaming
benchmark.

**PathfinderWiki** exposes the MediaWiki API: 27,749 articles, 15.4 M words, under Paizo's CUP.
Raw wikitext (not rendered extracts) is worth pulling because the `{{Person}}`/`{{City}}`/`{{Deity}}`
infoboxes carry structured lore the extract API discards.

After normalisation: **19.1 M tokens** (13.5 M rules + 5.6 M lore) and **403k outbound entity links**.
Tiny for pretraining, ample for retrieval — which already hints at the architecture.

## RAG vs fine-tune is the wrong axis

Two failure modes, two fixes:

| Failure | Fix |
| --- | --- |
| Doesn't know Vicious Swing's damage scaling at level 10 | **RAG.** 41k entities with exact numbers is a lookup problem; no fine-tune reliably memorises 41k stat blocks, and errata makes weights stale. |
| Answers "roll a d20, add proficiency bonus" and invents bonus actions | **Fine-tune.** A corrupted prior, not a missing fact. Retrieval doesn't remove a prior; it competes with one, and the prior often wins. |

Evidence for the hybrid rather than either pole:

- **RAFT** ([2403.10131](https://arxiv.org/abs/2403.10131)) trains on retrieved context *including
  distractors*, with CoT answers quoting the source verbatim. Near-perfect fit: "cite the AoN entry
  you used" is exactly the target behaviour.
- **EntiGraph synthetic CPT** ([2409.07431](https://arxiv.org/pdf/2409.07431), ICLR 2025) recovers
  >80% of RAG's gain parametrically and **stacks with** RAG.
- **Synthetic Mixed Training** ([2603.23562](https://arxiv.org/pdf/2603.23562)) reports +2.6% over
  RAG alone but **+9.1% combined**.
- **Low-resource knowledge injection** ([2508.06178](https://arxiv.org/pdf/2508.06178)) finds plain
  continued pretraining on a small corpus barely moves; *diverse synthetic rephrasing* is what lands.

**Decision: retrieval is load-bearing; a small LoRA does the three things retrieval cannot** — kill
the 5e prior, enforce Remaster vocabulary, teach grounded citation and abstention over retrieved
chunks. Do not try to memorise the rules into weights.

Corollary split: **rules → retrieval** (exact numbers, high precision). **Lore → parametric** is more
defensible (narrative, forgiving, few exact numbers), and is where EntiGraph-style synthetic CPT
over the link graph earns its keep.

## Model selection

Target hardware: RTX 5090, 32 GB VRAM, sm_120 Blackwell, 61 GB system RAM.

**Baseline: `Qwen/Qwen3.8-27B`** — Apache-2.0, 27.78 B dense params, 64 layers × 5120 hidden,
262k context, released 2026-08-05. At 4-bit that is ~14.5 GB of weights, leaving room for QLoRA at
moderate sequence length. The 248k vocabulary makes the loss head memory-hungry, so chunked
cross-entropy (Unsloth does this) matters more than usual.

Other Qwen3.8 checkpoints are not local options: `Qwen3.8-Flash-Next` is 180 B MoE and
`Qwen3.8-2.4T-A95B` is the flagship. `Qwen3.8-27B-FP8` is useful for fast *inference* when serving
the retrieval baseline, not for training.

Fallbacks if 27B QLoRA proves too tight to iterate on: `Qwen/Qwen3.5-9B` (has a base checkpoint,
trains fast enough for daily iteration) or `google/gemma-4-12B-it`.

Tooling: Unsloth has Blackwell support with sm_120-specific kernels — use the Studio install, not the
PyPI wheel, which has known sm_120 kernel gaps.

**Ceiling check before spending compute:** run the same benchmark against a frontier model with the
same retrieval. If frontier + retrieval already passes, the fine-tune only buys local/private/cheap,
and that should be a known fact rather than a discovery.

## The real gap is the benchmark

No PF2e benchmark exists. Building one is more reusable than any checkpoint, and it has to come
first — otherwise there is no way to tell whether the LoRA helped. See `eval/generate_benchmark.py`.
