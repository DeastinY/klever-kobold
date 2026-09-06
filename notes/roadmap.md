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

## Phase 1 — Baseline measurement ✅ done

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

**Exit criterion — answered.** `trap_5e` came back clean at 30/30 for both frontier models
(`gpt-5`, `gpt-4.1-mini`) but 25/30 for `Qwen3.8-27B`, which put death saving throws and 1-hour
short rests into Pathfinder rulings. The contamination premise is wrong about frontier models and
right about the one whose weights are ours to change. A thinking-mode control rules out the obvious
confound.
`lookup_*` is as bad as predicted — 1–17%, and *below the trivial baseline* on rarity. Abstention
turned out to be the discriminating axis nobody planned for: 33/40 fabricated levels for the small
model, 1/40 for the large one. Full numbers in [`notes/experiments.md`](experiments.md).

Still outstanding: the `Qwen3.8-27B` run, which is the one the premise actually depends on, and the
`Qwen3.5-9B` run to price iteration cost.

---

## Phase 2 — Retrieval ✅ done

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

**Exit criterion — answered.** R@5 is 92.5% overall (hybrid + the legacy→Remaster hop). With five
excerpts every model roughly triples: gpt-5 67.9%, Qwen3.5-9B 65.0%, Qwen3.8-27B and gpt-4.1-mini
63.2%. A 9B in 4-bit lands 2.9 points off gpt-5.

The gap turned out not to be a prior problem. Retrieval fixed the priors too — the 9B's applied-trap
grounding went 9% → 81%. What it did not fix is precision (`prereq`: 100% R@5, 21% accuracy,
over-answering on 61 of 80) and what it actively broke is abstention (Qwen3.8-27B 77.5% → 0.0%).
Full numbers in [`notes/experiments.md`](experiments.md).

---

## Phase 3 — RAFT LoRA ✅ done

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

**Exit criterion — revised after Phase 2.** `trap_5e` is off the list; retrieval solved it. The
adapter must move `prereq` (21.2%) and `lookup_traits` (57.5%) toward their 100% retrieval ceilings,
and drag `abstention` back from the collapse retrieval caused, without regressing `lookup_level`
(96.2%), `lookup_rarity` (96.2%) or `trap_5e` (100%).

Development target is **Qwen3.5-9B + retrieval at 65.0%** — faster to iterate than the 27B and
marginally better with retrieval anyway.

---

## Phase 4 — Query understanding ← next

The hand-written holdout (`eval/holdout.jsonl`) showed retrieval R@5 falling from 97.1% to 45.8%
when questions are phrased the way players phrase them, and BM25 from 88.5% to 20.0%. That is now
the binding constraint on everything.

- **Query rewriting / decomposition** before retrieval: turn "an ogre has grabbed my monk, what can
  she do?" into lookups for the grabbed condition and the Escape action.
- **A description→entity path** that does not rely on name overlap. The 403k-edge link graph and the
  `summary` field are both unused by the current retriever.
- **Route situational questions into the rules and action corpora**, not the entity corpus; 7.7% R@5
  on that family is the worst number in the project.
- Re-run the holdout after each change. It is 57 items and takes two minutes.

## Phase 5 — Lore continued pretraining (optional, probably skip)

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
