# Prior art

Surveyed 2026-09-06. Star counts and last-push dates as of that date.

## PF2e + LLM: everything that exists

Nobody has fine-tuned a language model on Pathfinder 2e. There is no PF2e model, no PF2e
rules or lore dataset, and no PF2e benchmark on HuggingFace. Everything below is retrieval.

### Retrieval components

| Project | What it is | Reach |
| --- | --- | ---: |
| [Kaylebor/pf2e-codex-embed-xs](https://huggingface.co/Kaylebor/pf2e-codex-embed-xs) | Snowflake Arctic-Embed xs fine-tune for PF2e retrieval. The only PF2e-adapted model of any kind on the Hub. | 93 dl |
| [Kaylebor/pf2e-codex-reranker](https://huggingface.co/Kaylebor/pf2e-codex-reranker) | Cross-encoder reranker | 3 dl |
| [Kaylebor/pf2e-codex-reranker-minilm](https://huggingface.co/Kaylebor/pf2e-codex-reranker-minilm) | MiniLM reranker variant | 2 dl |
| [Kaylebor/pf2e-codex-reranker-multilingual](https://huggingface.co/Kaylebor/pf2e-codex-reranker-multilingual) | Multilingual reranker variant | 1 dl |
| [Kaylebor/pf2e-codex-reranker-quantized](https://huggingface.co/Kaylebor/pf2e-codex-reranker-quantized) | Quantized reranker | 1 dl |

Worth benchmarking `pf2e-codex-embed-xs` against a strong general embedder in Phase 2 — it is the
only in-domain retriever anyone has published, and at 22M parameters it is nearly free to run.

### RAG assistants

| Project | Stack | Stars | Last push |
| --- | --- | ---: | --- |
| [MahmuudIbrahim/Pathfinder-Rules-LLM](https://github.com/MahmuudIbrahim/Pathfinder-Rules-LLM) | Pf2ools JSON + SRD markdown + AoN → ChromaDB → Claude/GPT, FastAPI + web UI | 0 | 2026-04-14 |
| [ClawedMaple/PF2e-RAG](https://github.com/ClawedMaple/PF2e-RAG) | Capstone project, PF2e RAG assistant | 0 | 2025-04-30 |
| [tvanfossen/pathfinder-society-scribe](https://github.com/tvanfossen/pathfinder-society-scribe) | Discord bot, local models, BDD-validated behaviour | 0 | 2025-12-14 |
| [wyrdsmith/agentic-pathfinder2e-module-generator](https://github.com/wyrdsmith/agentic-pathfinder2e-module-generator) | Adventure module generation with Pydantic AI | 0 | 2026-08-27 |
| [Simon-Stone/pf2e-fake-id](https://github.com/Simon-Stone/pf2e-fake-id) | Foundry module generating deliberately *wrong* creature identifications | 1 | 2026-02-04 |

None publishes an evaluation. `Pathfinder-Rules-LLM` is the closest neighbour to this project and
the most useful to read: same data sources, same chunking instinct, no measurement.

### Adjacent TTRPG RAG (not PF2e)

[Erickllino/RPG-RAG](https://github.com/Erickllino/RPG-RAG) ·
[riccjohn/grimoire-oracle](https://github.com/riccjohn/grimoire-oracle) ·
[DVDAGames/local-tabletop-ai-demo](https://github.com/DVDAGames/local-tabletop-ai-demo)
(5e SRD → Chroma, from a 2023 prompt-engineering talk).

### Benchmarks

No PF2e benchmark exists. The adjacent work measures different things:

- [D20bench](https://e4developer.com/posts/d20bench-benchmarking-llms-with-dungeons-and-dragons/) —
  LLMs fight each other under 5e SRD combat rules. Measures tactical decision-making, not rules recall.
- [RPGBench](https://arxiv.org/abs/2502.00595) — LLMs as text RPG *engines*: game creation and
  simulation, state tracking, rule enforcement.
- LudoBench — multimodal reasoning over tabletop game rules from a photo of a board state.

None of them measures "does the model know this system's rules", which is why
`eval/generate_benchmark.py` exists.

## Data sources

| Source | License | Notes |
| --- | --- | --- |
| [Archives of Nethys](https://2e.aonprd.com/) | ORC / Paizo CUP | **Used.** Anonymous Elasticsearch at `elasticsearch.aonprd.com`, 45,547 docs with pre-rendered markdown. |
| [PathfinderWiki](https://pathfinderwiki.com/) | Paizo CUP | **Used.** MediaWiki API, 27,749 articles of Golarion lore. |
| [Pf2ools/pf2ools-data](https://github.com/Pf2ools/pf2ools-data) | MIT | Structured game data with a [Zod schema](https://github.com/Pf2ools/pf2ools-schema). Best source for *programmatically verifiable* answers. |
| [foundryvtt/pf2e](https://github.com/foundryvtt/pf2e) | Apache-2.0 | 639★. Official Paizo partnership. JSON packs under `packs/`, plus the natural surface to ship a finished assistant into. |
| [Pf2eToolsOrg/Pf2eTools](https://github.com/Pf2eToolsOrg/Pf2eTools) | MIT | 136★. Long-running community data project. |
| [Obsidian-TTRPG-Community/Pathfinder-2E-SRD-Markdown](https://github.com/Obsidian-TTRPG-Community/Pathfinder-2E-SRD-Markdown) | CUP | 79★. Pre-Remaster (last push 2024-02) — useful as a *legacy* snapshot, not as current rules. |
| [wanderers-guide/wanderers-guide](https://github.com/wanderers-guide/wanderers-guide) | GPL-3.0 | Character builder; encodes prerequisite logic. |
| [521-studios/pfsrd2-data-api](https://github.com/521-studios/pfsrd2-data-api) | — | JSON/SQLite PF2e data API. |
| [skaldarnar/awesome-pf2e](https://github.com/skaldarnar/awesome-pf2e) | CC0 | The index to all of the above. |

## What this means

The gap is not the model — it is that no one has measured anything. Five RAG bots exist and not one
reports a number, so there is no published evidence about how well retrieval alone handles PF2e, and
no way for a sixth bot to know whether it is better than the fifth. That is the hole this project
fills first.
