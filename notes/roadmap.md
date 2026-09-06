# Roadmap

Ordering principle: **the benchmark comes before the model, and retrieval comes before the tune.**
Each phase produces a number that decides whether the next phase is worth doing.

---

## Phase 0 — Corpus ✅ done

- `scripts/dump_aon.py` → 45,547 AoN documents
- `scripts/dump_wiki.py` → 27,761 PathfinderWiki pages
- `scripts/build_chunks.py` / `build_wiki_chunks.py` → 64,347 chunks, 19.1 M tokens, 403k entity links
- `eval/generate_benchmark.py` → 470-item benchmark, 7 families

---

## Phase 1 — Baseline measurement ← next

**Build `eval/score.py`.** Graders per `answer_type`, all deterministic except one:

| `answer_type` | Grader |
| --- | --- |
| `int`, `exact` | normalised string match against `acceptable` |
| `set` | precision/recall over `acceptable`, report exact-set-match too |
| `abstain` | did the response refuse, or did it invent a feat? |
| `free` (`trap_5e`) | **`must_not_contain` is the primary metric** — a pure substring check for 5e vocabulary, no judge needed. An LLM judge scores substantive correctness as a secondary number. |

The `must_not_contain` design is deliberate: contamination is detectable without a judge, so the
headline number is cheap, reproducible, and not itself model-dependent.

**Then run three closed-book baselines** (no retrieval, same prompt):

1. `Qwen/Qwen3.8-27B` — the floor, and the 5e-contamination measurement that motivates the project.
2. A frontier model (Claude / GPT) — the **ceiling check**. If frontier + retrieval later clears the
   bar, the fine-tune only buys local/private/cheap. Know that before spending compute.
3. `Qwen/Qwen3.5-9B` — is the 27B worth the iteration cost?

**Exit criterion:** a per-family scoreboard. Expect near-zero on `lookup_*`, poor on
`remaster_rename`, and bad `trap_5e` contamination. If `trap_5e` is already clean, the whole
fine-tune premise is wrong and the project becomes retrieval-only — which is a good thing to learn
in week one.

---

## Phase 2 — Retrieval

The benchmark hands us **free retrieval labels**: 400 of the 470 items carry `source_ids` naming the
exact gold chunk. Recall@k is measurable without annotating anything.

- **Index** entity-level chunks (never token-window splits — each AoN entry is already atomic).
- **Hybrid** BM25 + dense, with hard metadata filters on `level`, `traits`, `category`,
  `remaster_status`. Filtering is where this corpus beats naive vector search: "level 4 fighter feats
  with the flourish trait" is a filter, not a similarity query.
- **Default `remaster_status != legacy`** unless the query asks for legacy content.
- **Embedder bake-off**: `Kaylebor/pf2e-codex-embed-xs` (the only existing PF2e-tuned embedder) vs a
  strong general model, scored on recall@{1,5,20}.
- Re-run the benchmark **with** retrieval.

**Exit criterion:** retrieval recall@5 and the with-retrieval scoreboard. The gap between
"gold chunk was retrieved" and "answer was right" is the exact size of the prior problem — and the
justification for Phase 3.

---

## Phase 3 — RAFT LoRA

Train on retrieved context, not on raw rules text.

- **Synthesise** training items: question + k chunks (1 gold + distractors) + a CoT answer that
  quotes the source verbatim and cites the AoN URL. Generate with a teacher model over AoN entries
  held out from the benchmark.
- **Deliberately include**: unanswerable questions (abstention), legacy-name questions whose correct
  answer is the Remaster name, and items where *all* retrieved chunks are distractors.
- **Train** QLoRA on `Qwen/Qwen3.8-27B` with Unsloth Studio (sm_120 kernels; chunked cross-entropy
  matters at 248k vocab). Start rank 16–32, LR ~1e-4, ≤3 epochs, checkpoint often.
- **Strict hygiene:** the benchmark's `source_ids` are excluded from training generation. No entity
  in the test set contributes a training item.

**Exit criterion:** does the LoRA beat base+retrieval on `trap_5e` and `abstention` without
regressing `lookup_*`? Those are the two families that measure prior, not knowledge.

---

## Phase 4 — Lore continued pretraining (optional, gated on Phase 3)

Only worth doing if Phase 3 shows the model can hold PF2e framing. Lore is where parametric
knowledge is actually appropriate — narrative, forgiving, few exact numbers.

- EntiGraph-style synthetic CPT over the 403k-edge entity graph plus wiki infoboxes: sample entity
  pairs, generate text relating them, train on the synthetic corpus.
- Needs a **lore eval that does not exist yet** — build it from wiki infobox fields (ruler of X,
  deity of Y, capital of Z) the same way the rules benchmark was built from AoN fields.

---

## Phase 5 — Serving

- vLLM with the FP8 weights, or GGUF via llama.cpp for a smaller footprint.
- Surface it where it gets used: an MCP server for rules lookup, or a Foundry VTT module
  (`foundryvtt/pf2e` is Apache-2.0 and officially partnered with Paizo).
- Every answer cites its AoN URL. Non-negotiable — it is both the trust mechanism and the
  attribution mechanism.

---

## Cross-cutting

- **Freeze the test split now.** `eval/benchmark.jsonl` is generated with a fixed seed
  (`--seed 20260906`) and committed. Regenerating with a different seed creates a *new* benchmark;
  it does not replace this one.
- **Corpus refresh**: AoN publishes errata continuously. Re-run the dump before any headline number
  and record `data/processed/corpus_stats.json` alongside results.
- **Track every run** with the corpus stats hash, model id, retrieval config, and per-family scores.
  Seven numbers per run, not one.
