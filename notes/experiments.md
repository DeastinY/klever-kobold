# Experiment log

Every run records the model, the prompt, the corpus build it was scored against, and the
per-family numbers. One number is never enough for this benchmark: a model that refuses
everything scores 100% on `abstention` and 0% on everything else.

## Trivial baselines

What a model that knows nothing about Pathfinder scores (`eval/baselines.py`):

| Family | n | Trivial strategy | Score |
| --- | ---: | --- | ---: |
| `lookup_level` | 80 | always answer "1" | 13.8% |
| `lookup_rarity` | 80 | always answer "uncommon" | **70.0%** |
| `lookup_traits` | 80 | no constant set matches | 0% |
| `prereq` | 80 | no constant set matches | 0% |
| `remaster_rename` | 80 | most common answer | 2.5% |
| `abstention` | 40 | refuse everything | 100% |
| `trap_5e` | 30 | say nothing | 100% |
| `trap_5e_applied` | 16 | say nothing | 100% |

`lookup_rarity` at 70% is the important one. Neither frontier model beat it.

---

## Run 1 — `gpt-4.1-mini`, closed-book

2026-09-06 · 470 items · 35k in / 16k out · 48s · non-reasoning

| Family | Correct | Accuracy | Notes |
| --- | ---: | ---: | --- |
| `lookup_level` | 4/80 | 5.0% | |
| `lookup_traits` | 0/80 | 0.0% | recall 22%, over-answered on 64 |
| `lookup_rarity` | 46/80 | 57.5% | **below the 70% trivial baseline** |
| `prereq` | 0/80 | 0.0% | recall 4%, over-answered on 71 |
| `remaster_rename` | 10/80 | 12.5% | |
| `abstention` | 2/40 | 5.0% | **invented a level for 33 of 40 non-existent feats** |
| `trap_5e` | 30/30 | 100% | no 5e vocabulary at all |
| `trap_5e_applied` | 12/16 | 75.0% | **4 genuine leaks**, PF2e machinery present 43% |
| **Overall** | **104/486** | **21.4%** | |

## Run 2 — `gpt-5`, closed-book

2026-09-06 · 470 items · 35k in / 349k out · 8m15s · `reasoning_effort=low`, retried 15 truncations at
6k tokens

| Family | Correct | Accuracy | Notes |
| --- | ---: | ---: | --- |
| `lookup_level` | 14/80 | 17.5% | |
| `lookup_traits` | 1/80 | 1.2% | recall 16%, over-answered on 20 |
| `lookup_rarity` | 25/80 | 31.2% | **less than half the trivial baseline** |
| `prereq` | 2/80 | 2.5% | recall 10%, over-answered on 57 |
| `remaster_rename` | 5/80 | 6.2% | |
| `abstention` | 31/40 | 77.5% | invented a level once |
| `trap_5e` | 30/30 | 100% | no 5e vocabulary at all |
| `trap_5e_applied` | 15/16 | 93.8% | 1 leak, PF2e machinery present 78% |
| **Overall** | **123/486** | **25.3%** | |

## Run 3 — `Qwen/Qwen3.8-27B`, closed-book *(the run the premise depended on)*

2026-09-06 · 486 items · nf4 4-bit, `enable_thinking=false`, greedy, batch 16, 500 max tokens ·
11m45s on one RTX 5090 · 22.9 GB VRAM

| Family | Correct | Accuracy | Notes |
| --- | ---: | ---: | --- |
| `lookup_level` | 9/80 | 11.2% | |
| `lookup_traits` | 0/80 | 0.0% | recall 9%, over-answered on 50 |
| `lookup_rarity` | 15/80 | 18.8% | far below the 70% trivial baseline |
| `prereq` | 1/80 | 1.2% | recall 3%, over-answered on 64 |
| `remaster_rename` | 11/80 | 13.8% | best of the three, oddly |
| `abstention` | 31/40 | 77.5% | fabricated 3 levels — matches gpt-5, beats gpt-4.1-mini by 30x |
| `trap_5e` | 25/30 | 83.3% | **5 leaks — the only model that fails this family** |
| `trap_5e_applied` | 13/16 | 81.2% | 3 leaks, PF2e machinery present **36%** |
| **Overall** | **106/486** | **21.8%** | |

The five quiz leaks:

| Topic | Leak |
| --- | --- |
| dying | "they become **Unconscious** and begin making **Death Saving Throws**" |
| hit points | invented a "**Short Rest:** Typically 1 hour" |
| focus spells | Focus Points "recovered when you rest (short rest or long rest)" — it is Refocus |
| multiple attack penalty | stated as **-4 on both** second and third Strike; it is -5 and -10 |
| encumbrance | *false positive* — "instead of using weight (pounds/kilograms)" is a denial; fixed the separator set |

## Run 3b — `Qwen/Qwen3.8-27B`, thinking control

Trap families only, `enable_thinking=true, reasoning_effort=low`, 2000 max tokens.

| Family | Thinking off | Thinking on |
| --- | ---: | ---: |
| `trap_5e` | 83.3% | 90.0% |
| `trap_5e_applied` | 81.2% | 81.2% |
| grounding (applied) | 36% | 30% |

Reasoning helps a little on the quiz family and not at all on adjudication. **Contamination is not
an artifact of disabling thinking**, which was the obvious confound and is now ruled out.

## Run 4 — `Qwen/Qwen3.5-9B`, closed-book

2026-09-06 · 486 items · nf4 4-bit, `enable_thinking=false`, greedy, batch 24 · **4m41s** (2.5x
faster than the 27B)

| Family | Correct | Accuracy | Notes |
| --- | ---: | ---: | --- |
| `lookup_level` | 7/80 | 8.8% | |
| `lookup_traits` | 0/80 | 0.0% | recall 14%, over-answered on 73 |
| `lookup_rarity` | 18/80 | 22.5% | |
| `prereq` | 0/80 | 0.0% | recall 3%, over-answered on 72 |
| `remaster_rename` | 9/80 | 11.2% | |
| `abstention` | 11/40 | 27.5% | fabricated 21 levels |
| `trap_5e` | 21/30 | 70.0% | **9 leaks** |
| `trap_5e_applied` | 11/16 | 68.8% | 5 leaks, PF2e machinery present **9%** |
| **Overall** | **77/486** | **15.8%** | |

## The gradient

Contamination is not a yes/no property. It scales monotonically with capability across every trap
measure:

| Model | `trap_5e` clean | applied clean | applied grounding | fabricated levels |
| --- | ---: | ---: | ---: | ---: |
| gpt-5 | 100% | 93.8% | 78% | 1/40 |
| gpt-4.1-mini | 100% | 75.0% | 43% | 33/40 |
| Qwen3.8-27B | 83.3% | 81.2% | 36% | 3/40 |
| Qwen3.5-9B | 70.0% | 68.8% | 9% | 21/40 |

Grounding is the cleanest signal in the whole benchmark: 78 / 43 / 36 / 9. The 9B names the right
Pathfinder machinery in *one ruling out of eleven*.

Abstention is the one column that does not follow the gradient — it tracks neither size nor
knowledge. All four models know equally little; only their willingness to say so differs.

## Reading

**Contamination is an open-weight problem, and it depends on how you ask.** The v1 traps quiz the model — "does
Pathfinder use advantage?" — and both models scored 30/30. The question telegraphs that the answer is
no. So a second family (`trap_5e_applied`, 16 items) was written that asks the model to *adjudicate a
situation* and checks whether 5e machinery turns up in the ruling. The separation was immediate:
75% clean for gpt-4.1-mini against 93.8% for gpt-5, and 43% vs 78% on whether the correct Pathfinder
machinery appeared at all.

All five leaks are genuine, not metric artifacts:

| Model | Topic | Leak |
| --- | --- | --- |
| gpt-4.1-mini | sustained spells | "they must attempt a **Concentration check** to maintain the spell" — no such mechanic in PF2e |
| gpt-4.1-mini | between-encounter healing | invented a "10-minute **short rest**" |
| gpt-4.1-mini | spell ranks | "1st-level spells / 2nd-level spells / 3rd-level spells" — Remaster uses ranks |
| gpt-4.1-mini | critical saves | **"They take half damage"** on a natural 20 Reflex save — misses that a nat 20 raises the degree to critical success, which means *no* damage |
| gpt-5 | spell ranks | "2 third-level spell slots" — terminology only |

The fourth is the important one. That is not a vocabulary slip, it is a wrong ruling produced by the
5e prior, on a situation that comes up constantly at a table.

**The premise survives where it matters.** It is wrong about frontier models — they pass the quizzes
outright and mostly hold up under adjudication — and right about Qwen3.8-27B, the model whose weights
are actually ours to change. It is the only one that fails the quiz family, and it does so by putting
death saving throws and 1-hour short rests into Pathfinder rulings. On the applied family it names
the correct Pathfinder machinery in 36% of rulings against gpt-5's 78%.

The frontier advantage overall is small — 25.3% vs 21.8% — and it sits in abstention and calibration
rather than knowledge. Nobody knows this corpus. That is the case for retrieval; the fine-tune only
has to buy behaviour.

**Closed-book lookup is hopeless at any scale.** 1–17% across the recall families, and *below the
trivial baseline* on rarity for both models. Retrieval is not an optimisation here.

**Abstention is a capability axis, not a knowledge one.** Identical missing knowledge, opposite
behaviour: gpt-4.1-mini fabricated 33 levels out of 40, gpt-5 fabricated 1. This is exactly the kind
of behaviour a fine-tune teaches and retrieval cannot.

## Metric bugs found and fixed

Reading the responses rather than the scores caught two false positives, both inflating measured
contamination — the number this project exists to argue about, so both were flattering to the
premise:

1. **Question echo.** "Does the game have an Insight skill?" cannot be answered without the phrase
   "Insight skill". Scored four correct refutations as contamination, and scored `remaster_rename`
   at 80/80 "used the legacy name" when the legacy name is in every one of those questions by
   construction.
2. **Denial counted as use.** "Pathfinder does not use hit dice" is the right answer.

Also fixed: matching is now plural-tolerant ("there are no bonus actions" must count as a mention),
and an empty response can never score — under a negative check like `trap_5e`, a truncated run was
silently scoring as a clean one. gpt-5 had 15 truncations at a 1500-token cap, five of them in
`trap_5e`; they were re-run at 6k.

## Benchmark changes

- **v1 → v2**: added `trap_5e_applied` (16 items). The 470 v1 items are unchanged and keep their
  ids, so per-family numbers stay comparable across versions; only the overall denominator moved
  (470 → 486). Both frontier runs were re-run on the new family and merged rather than re-scored
  from stale responses.

---

# Phase 2 — retrieval

## Retriever comparison

400 benchmark items carry a gold chunk id. No annotation, no judge.

| Retriever | Mode | R@1 | R@5 | R@20 | MRR |
| --- | --- | ---: | ---: | ---: | ---: |
| — | bm25 | 69.2% | 84.5% | 88.8% | 0.759 |
| — | bm25+hop | 68.5% | 89.0% | 92.0% | 0.768 |
| `pf2e-codex-embed-xs` | dense | 67.5% | 82.5% | 89.5% | 0.740 |
| `arctic-embed-xs` (its base) | dense | 67.5% | 82.5% | 89.5% | 0.740 |
| `Qwen3-Embedding-0.6B` | dense | 65.8% | 86.8% | 92.5% | 0.744 |
| `pf2e-codex-embed-xs` | hybrid+hop | 78.0% | 92.5% | 95.0% | 0.839 |
| `Qwen3-Embedding-0.6B` | hybrid+hop | 76.5% | **92.8%** | 96.8% | 0.837 |

### The hop

`remaster_rename` sat at 46.2% R@5 while every other family was at 97–100%. Those questions name the
*old* entity, so both retrievers land on the legacy chunk — the one that must never be served as
current rules. Filtering legacy out first makes it worse: that chunk is the only one carrying
`remaster_id`, the pointer to its replacement. Retrieve it, then hop. 46.2% → 65.0% for the family,
88.8% → 92.5% overall.

### The embedder bake-off

`Kaylebor/pf2e-codex-embed-xs` and `Snowflake/snowflake-arctic-embed-xs` — the fine-tune and its own
base — score **identically to three decimals across 400 queries**. Checked at the weight level:

- largest weight difference across all 101 shared tensors: **3.1e-4**
- corpus embeddings: mean cosine **1.0**, max element difference **6.8e-5**

That is precision-round-trip magnitude. On this benchmark the only published PF2e retriever conveys
no measurable advantage over its base. Practical upshot is still cheerful: the 22M model indexes the
corpus in 28s and is within half a point of `Qwen3-Embedding-0.6B` at 213s.

## Retrieval-augmented runs (k=5, hybrid+hop)

> **Corrected 2026-09-06 after a fifth scorer bug.** The over-answering check was applied to
> `prereq`, whose gold set is not drawn from the trait vocabulary. "Dedication" is both a trait name
> and part of most correct prerequisite answers, so "Sleepwalker Dedication" — exactly right — was
> scored wrong. This understated every retrieval run by ~15 points and invented the "30-point
> precision gap" this project believed in for several hours. Numbers below are post-fix.

| Model | Closed-book | + retrieval | Δ |
| --- | ---: | ---: | ---: |
| **Qwen3.5-9B** | 17.4% | **84.3%** | 4.8x |
| gpt-5 | 27.5% | 83.2% | 3.0x |
| Qwen3.8-27B | 23.1% | 82.6% | 3.6x |
| gpt-4.1-mini | 22.9% | 81.9% | 3.6x |
| gpt-6-astra | **31.6%** | — | credits exhausted |

**A 9B in 4-bit on one desktop card is the best model on this benchmark**, ahead of gpt-5. Not by
much, and within noise of the other three — but the honest reading is that with good retrieval this
task does not discriminate between a 9B and a frontier model.

### Per family, with retrieval

| Family | gpt-5 | Qwen3.5-9B | retrieval R@5 |
| --- | ---: | ---: | ---: |
| `lookup_level` | 87.5% | 96.2% | 100% |
| `lookup_rarity` | 96.2% | 96.2% | 97.5% |
| `trap_5e` | 96.7% | 96.7% | — |
| `trap_5e_applied` | 100% | 93.8% | — |
| `lookup_traits` | 86.2% | 87.5% | 100% |
| `prereq` | 91.2% | 82.5% | 100% |
| `remaster_rename` | 77.4% | 73.6% | 88.7% |
| `abstention` | **17.5%** | **35.0%** | — |

Everything except abstention is between 73% and 97%. Abstention alone accounts for roughly half of
all remaining errors on 8.7% of the items.

## Reading phase 2

**The thesis was half wrong.** "Retrieval fixes facts, fine-tuning fixes priors" — retrieval fixed
the priors too. Qwen3.5-9B's applied-trap grounding went from **9% to 81%** and its quiz leaks from
nine to zero. A model reading the correct rules entry does not reach for 5e. It never needed its
prior corrected; it needed the page.

**Retrieval created a new failure.** Abstention collapsed: gpt-5 77.5% → 17.5%, Qwen3.8-27B
77.5% → **0.0%** (27 of 40 fabricated levels, up from 3). Hand a model five plausible neighbouring
feats and ask about one that was never written, and it answers about a neighbour. The distractors
are now in the prompt looking authoritative.

**~~The residual gap is precision~~ — retracted.** That claim was a scorer bug (see above). With the
grader fixed, `prereq` is 82–91% and `lookup_traits` 86–88%. Precision is fine.

**The residual gap is abstention, and only abstention.** 17.5% for gpt-5, 35.0% for the 9B, 0.0% for
the 27B. This is a known, hard, and specifically-RAG-caused failure:

- [RefusalBench](https://arxiv.org/abs/2510.10390) (EACL 2026, 30+ models): refusal accuracy below
  50% on multi-document tasks; **neither scale nor extended reasoning helps**. But refusal is
  "a trainable, alignment-sensitive capability".
- [Prompt-Based Abstention Fails Under Misleading Context](https://arxiv.org/html/2608.22228) (2026):
  small RAG models abstain 97–99% when context is *missing*, and answer 13.6–74.3% of the time when
  it is *misleading*. Our abstention family is the misleading case — five plausible neighbours.
  Their strongest prompt-only mitigation cuts the answer rate to 13.3% but **discards 49.8% of
  correct answers on answerable questions**.
- [Divide-Then-Align](https://arxiv.org/pdf/2505.20871): warns that RAFT *itself* trains models to
  answer when reliable knowledge is unavailable, and proposes DPO over four knowledge quadrants
  instead. Direct caution for phase 3: SFT alone may not be enough, and could hurt.

**`remaster_rename` is the one family still retrieval-bound**: 65% R@5, and every model sits at
43–50%, i.e. roughly at its ceiling. Improving it means better retrieval, not a better model.

## Targets for phase 03

**Revised after phase 2.** Contamination is off the list — retrieval solved it. The adapter has two
jobs left, both behavioural, both exactly what RAFT trains: *use the one relevant excerpt and ignore
the other four*, and *say it does not exist when it is in none of them*.

Baseline is Qwen3.5-9B + retrieval (65.0% overall), the development target: 2.5x faster to evaluate
than the 27B and slightly better with retrieval anyway.

| Metric | Now | Ceiling | Gap |
| --- | ---: | ---: | --- |
| `prereq` | 21.2% | 100% R@5 | pure precision — the answer is in the prompt |
| `lookup_traits` | 57.5% | 100% R@5 | over-answered on 31 of 80 |
| `abstention` | 35.0% | — | must survive distractors, not be destroyed by them |
| `remaster_rename` | 50.0% | 65% R@5 | near ceiling; needs retrieval work, not training |
| `trap_5e_applied` | 93.8% | 100% | mostly solved by retrieval |

Do not regress: `lookup_level` 96.2%, `lookup_rarity` 96.2%, `trap_5e` 100%.

---

# Phase 3 — the RAFT LoRA

`Qwen/Qwen3.5-9B` + QLoRA rank 32 on the text decoder, 2,600 RAFT items, 2 epochs, 1h49m on one
RTX 5090. Final eval loss 0.043, token accuracy 98.2%.

| Family | base + RAG | + RAFT LoRA | Δ |
| --- | ---: | ---: | ---: |
| `abstention` | 35.0% | **100.0%** | **+65.0** |
| `prereq` | 82.5% | 98.8% | +16.3 |
| `remaster_rename` | 73.6% | 77.4% | +3.8 |
| `lookup_level` | 96.2% | 100.0% | +3.8 |
| `lookup_traits` | 87.5% | 90.0% | +2.5 |
| `lookup_rarity` | 96.2% | 97.5% | +1.3 |
| `trap_5e_applied` | 93.8% | 100.0% | +6.2 |
| `trap_5e` | 96.7% | 93.3% | **−3.4** |
| **Overall** | **84.5%** | **94.6%** | **+10.1** |

For comparison, gpt-5 with the same retrieval scores 83.7%.

Fabricated levels on non-existent feats went from 23 of 40 to **zero**.

## The caveat, and the cross-check

The benchmark and the training data come out of the same generator. No entity appears in both — that
is enforced and verified — but the *shape* of a correct answer is shared, and the grader was written
against that shape. Some of the +10.1 is house style.

So the honest cross-check is a measurement with no generated text in it: the selection probe shows
the model the same five excerpts and reads the logits for six tokens (`1 2 3 4 5 N`).

| Selection accuracy | overall | abstention | chose N (51 correct) |
| --- | ---: | ---: | ---: |
| Qwen3.5-9B | **80.1%** | 100% | 89 |
| Qwen3.5-9B + RAFT LoRA | 78.5% | 100% | 63 |

**The adapter did not get smarter; it learned to behave.** Forced to choose, the *base* model already
identifies "none of these" on 40 of 40 abstention items — it knew the feat was absent and would not
say so in prose. The LoRA selects no better (78.5% vs 80.1%) and answers far better (94.6% vs 84.5%).
It is better calibrated about when to refuse (63 N-choices vs 89, against 51 correct).

This is the division of labour the project predicted for fine-tuning, reached from the opposite
direction than expected: not correcting a false prior, but converting knowledge the model already had
into behaviour it would actually perform.

## Costs

- `trap_5e` slipped 96.7% → 93.3% (2 items).
- Applied-trap grounding — the share of rulings naming the correct Pathfinder machinery — fell
  **81% → 58%**. Answers became terser. The adapter is more accurate and less forthcoming, which
  accuracy does not capture and a user would notice.

## Seventh scorer bug

`lookup_level` first scored **23.8%** for the LoRA against 96.2% for the base. The LoRA's answers
were correct — "Cleansing Transformation is 14th level" — and the grader could not match an ordinal
against `"14"`. The adapter had faithfully learned the ordinal phrasing from *my own training
template*, which also generated "1th level" and "2th level". Both fixed: `norm()` now folds ordinals,
and the template computes real ordinals. Five exact-match cases added to `eval/test_score.py`.

## Pending

- Phase 3: RAFT training data generation and the first LoRA.
- `remaster_rename` retrieval is the one place more indexing work still pays: 65% R@5 caps every
  model at ~50%.

---

# Phase 4 — the hand-written holdout

87.7% of the generated benchmark's retrieval questions name their target verbatim, and BM25 alone
scored 88.5% R@5 on it. That is a keyed lookup, not a question. `eval/seeds/natural_holdout.jsonl`
is 57 questions written by hand in player language, over entities from the same pool the LoRA's
training data excluded — so a drop isolates *phrasing*. Only 25% name their target.

## Retrieval collapses

| Retriever | generated R@5 | hand-written R@5 |
| --- | ---: | ---: |
| bm25 only | 88.5% | **20.0%** |
| hybrid+hop, `pf2e-codex-embed-xs` (22M) | 97.1% | 39.6% |
| hybrid+hop, `Qwen3-Embedding-0.6B` | 97.9% | **45.8%** |

Per family (best retriever): comparative 83.3%, legacy 71.4%, descriptive 55.6%, false-premise 25%,
**situational 7.7%**. "An ogre has grabbed my monk, what can she do?" does not retrieve `Escape`.

This also reverses the phase-2 embedder conclusion. The 0.6B model was worth 0.8 points on generated
questions and is worth **6.2** here. When names stop matching, semantics start earning their keep.

## The adapter does not transfer

| Family | base | + RAFT LoRA |
| --- | ---: | ---: |
| `nl_comparative` | 100% | 100% |
| `nl_situational` | 100% | 92.9% |
| `nl_legacy` | 87.5% | 50.0% |
| `nl_false_premise` | 72.7% | **81.8%** |
| `nl_descriptive` | 61.1% | 55.6% |
| **Overall** | **80.7%** | **73.7%** |

**+10.1 on the generated benchmark, −7.0 here.**

### The defence, tested and rejected

It could be argued the adapter is refusing more honestly when retrieval fails. Splitting by whether
the gold chunk was actually retrieved:

| | gold retrieved | gold not retrieved | refused when missed |
| --- | ---: | ---: | ---: |
| base | **21/22 (95%)** | 19/26 (73%) | 8/26 |
| + RAFT LoRA | 18/22 (82%) | 17/26 (65%) | 4/26 |

Worse in both halves, and refusing *less* often on failed retrievals. It is overfitting to a question
shape, not increased honesty.

### What did generalise

Refusal on genuinely non-existent entities: 72.7% → 81.8%, fabricated levels 2 → 0. The behaviour the
adapter was built for transferred. General answering did not.

## Honest state of the project

- Well-formed lookup questions: **84.5%** for 9B + retrieval, beating gpt-5's 83.7%.
- Questions phrased the way people ask them: **80.7%**, base model, no adapter.
- Bounded by a retriever that finds the right page **45.8%** of the time.

The next work is query understanding, not more training. Concretely: query rewriting or
decomposition before retrieval, a description→entity path that does not depend on name overlap, and
for situational questions a route into the rules/action corpus rather than the entity corpus.

---

# Phase 5 — query understanding, and a deployable system

The holdout grew from 57 to **109 hand-written questions** (89 with a gold entity,
37% naming it verbatim against the generated benchmark's 88%). Every number below
is on that set. Tuning against 48 items had become the limiting factor: the RRF
smoothing sweep moved results by less than its own noise.

## Retrieval

| Configuration | R@1 | R@5 | R@20 | MRR |
| --- | ---: | ---: | ---: | ---: |
| bm25 only | 7.9% | 19.1% | 28.1% | 0.130 |
| hybrid + hop (phase 2 best) | 22.5% | 47.2% | 64.0% | 0.337 |
| + summary index | 32.6% | 59.6% | 67.4% | 0.422 |
| + hypothetical summary | 37.1% | 64.0% | 78.7% | 0.499 |
| + category routing | **49.4%** | **76.4%** | **82.0%** | **0.610** |

Per family at the best setting: comparative 100%, legacy 90%, **situational 77.4%**
(was 7.7%), descriptive 66.7%.

**What worked, in order of contribution:**

1. **Category routing (+12.4).** The rewriter names up to three entry kinds and
   retrieval narrows to them. Equipment and creatures are two thirds of the corpus
   and answer almost none of these questions.
2. **Hypothetical summaries (+4.4).** Ask the model for the one-line summary the
   answering entry would have, and match it against the summary index. Both sides
   of that comparison are then one-line descriptions.
3. **The summary index (+12.4).** Name plus one-line summary, embedded alone. A
   6-second build.

**What did not work, tested and dropped:**

- *Asking the model to name the rules elements.* Produced "Path of the Totem
  Warrior" and "Daring Attack", neither of which exists. Naming is this model's
  worst measured skill on this corpus.
- *Upweighting the hypothetical-summary rankings.* w=1 beat 1.5, 2, 3 and 5. The
  single-query intuition that motivated it did not generalise.
- *Embedding the hypothetical summary as a document rather than a query.* No
  difference; the target ranked first either way.
- *Tuning RRF smoothing.* 60 → 5 is worth about two points, inside the noise of
  the sample it was measured on.

## Which model rewrites

| Rewriter | R@5 |
| --- | ---: |
| Qwen3.8-27B | 77.1% |
| Qwen3.5-9B | 70.8% |
| Qwen3.5-4B | 58.3% |

*(measured on the 57-item holdout, before it was widened)*

The 9B costs 6 points against the 27B; the 4B costs 19. Since the rewriter must
run on the laptop, this decided the shipped model.

## End to end

| System | Score |
| --- | ---: |
| **Deployed runtime (Ollama, k=8)** | **85.3%** |
| Lab path (transformers, nf4, k=5) | 84.4% |
| Deployed runtime, k=5 | 81.7% |
| Deployed runtime, k=12 | 80.7% |
| Base + phase-2 retrieval (57-item holdout) | 80.7% |
| RAFT LoRA + phase-5 retrieval | 81.7% |

Two things worth stating plainly:

**The deployed runtime matches the lab.** 85.3% through Ollama with Q4 weights and
float16 embeddings, against 84.4% through transformers with nf4 and float32. The
quantised chain costs nothing measurable. Average 1.65 s per question.

**The LoRA still loses.** 81.7% against the base model's 84.4% on the same
retrieval. It fixes fabrication (4 → 0 invented levels) and costs legacy questions
(85.7% → 57.1%) and grounding (situational machinery 71% → 48%). **Shipping
without it.** The adapter remains the clearest result of the project: it was
worth +10 on a benchmark generated by the same pipeline that trained it, and
negative on questions written by hand.

**k=8 excerpts.** 5 → 81.7%, 8 → 85.3%, 12 → 80.7%. An inverted U: recall@20
exceeds recall@5, so more excerpts keep finding the answer until enough irrelevant
ones accumulate to drown it.

## Deployment

Ollama holds `qwen3.5:9b` (5.7 GB) and `qwen3-embedding:0.6b` (0.6 GB). The Python
side is httpx, numpy and orjson — 59 MB installed, verified in a clean virtualenv
with torch absent and the GPU hidden. The index is 244 MB of float16 and loads by
memory-map in 0.21 s. About 6.6 GB resident on a 16 GB machine.

Qwen 3.6 and 3.8 cannot be deployed here: neither ships anything below 27B dense
or 35B-A3B, whose smallest usable quantisations are 13.6 GB and 16.6 GB. Both are
used for development work on the workstation.

## Two more measurement bugs

Nine and ten for the session, both caught by an implausible number rather than a
failing test:

- **Query-time category filtering counted its own mistakes as "unreachable".**
  The first run reported 76.9% over 13 scored items instead of 48. Reachability is
  now measured against the corpus-level filter only, so a filter that hides the
  answer cannot score better than one that does not.
- **Duplicate entries split an entity's evidence during rank fusion.** Cat Fall is
  ranked first by two of five views and came fourth after fusion, because two
  identical rows each carried half its score. Rankings now collapse to one
  canonical row per (name, category) before fusion — and the evaluator had to
  learn the same lesson, scoring 25% until it matched gold by canonical position
  instead of chunk id.

---

# Tier 0, increment 1 — a benchmark nobody here wrote

`eval/wild.jsonl`: **300 real Pathfinder 2e questions** from RPG StackExchange, with
gold entries taken from the Archives of Nethys pages the *accepted answer* links
to. Neither the questions nor the labels come from this project.

`scripts/mine_wild_questions.py` builds it. 730 questions fetched, 574 with an
accepted answer, 397 of those linking AoN, 300 kept after requiring one to four
resolvable entry links.

An earlier version matched entry *names* against the answer prose and produced
labels like "Advanced Player's Guide, Treasure by Level" for a question about
weapon runes. Name matching in free text is too noisy to be a benchmark. Links
are not.

## Thirteenth measurement bug: labels age

Most mined answers were written before the Remaster and cite legacy pages. The
retriever deliberately returns the entry that *superseded* a legacy page, so
doing the right thing was scored as a miss. Gold matching now accepts either side
of the Remaster relation.

This was worth more on the hand-written set than on the wild one:

| | before | after |
| --- | ---: | ---: |
| hand-written holdout R@5 | 76.4% | **80.9%** |
| wild R@5 | 26.0% | 27.0% |

(Also fixed: the summary line reported the first mode's unreachable count as if it
were global, which made a no-hop baseline's 201 look like a property of the whole
run.)

## The wild set says the pipeline is overfit to entity lookup

| Configuration | wild R@5 | hand-written R@5 |
| --- | ---: | ---: |
| hybrid + hop | 26.0% | 47.2% |
| hybrid3 + hop | **27.0%** | 59.6% |
| hybrid3 + hyde + cat + hop | 19.0% | **80.9%** |

**The full pipeline is the best configuration on questions I wrote and the worst
on questions I did not.** Same labels and same noise within each column, so the
ordering is trustworthy even though the absolute numbers are not comparable:
wild labels are incidental citations and many wild questions are discussion
rather than lookup.

The likely cause is specific. Wild questions are frequently about rules
*concepts* — "Is a Critical Failure a Failure?" cites the Playing the Game rules
page — while category routing narrows to entity kinds and HyDE writes a summary
in the shape of an *entry*. Both help when the answer is a feat and hurt when it
is a rules section.

**Next increment:** make narrowing conditional — never exclude the `rules`
category, and skip narrowing entirely when the rewriter's suggested kinds look
like a concept question. Gate on the hand-written holdout, confirm on wild.

## Tier 1, increment 2 — fuse the narrowed and unnarrowed rankings

The wild set said category narrowing blinds concept questions. Two fixes tried.

**Rejected: never exclude the rules category.** The hypothesis was right about wild
and wrong about the gate.

| always-allow | hand-written R@5 | wild R@5 |
| --- | ---: | ---: |
| none | **80.9%** | 19.0% |
| rules | 77.5% | 25.0% |
| rules + class-feature + trait | 76.4% | **27.0%** |

Nine points of wild recall for four and a half points of the gate. Not kept.

**Kept: fuse both rankings instead of choosing.** Run retrieval narrowed *and*
unnarrowed and fuse all of it by reciprocal rank. One extra scan of a
memory-mapped matrix, no additional model call.

| | hand-written | wild |
| --- | ---: | ---: |
| narrow only, R@8 | 82.0% | 22.0% |
| **fused, R@8** | **83.1%** | **31.0%** |

### The methodology error underneath

Fused retrieval looked like a regression at first — hand-written R@5 fell 80.9% →
76.4% — and it was only better at R@1, R@20 and MRR. Fusion reorders inside the
top twenty, moving some answers from rank 4 to rank 6.

**The deployed system retrieves eight excerpts.** Every retrieval decision in this
project had been gated at R@5, a point the product does not use. At R@8 the change
is an improvement on both sets. `KS` now includes 8 and the summary ranks by it.

### End-to-end

| | before | after |
| --- | ---: | ---: |
| **deployed, holdout** | 89.0% | **89.9%** |
| descriptive | 72.7% | 75.8% |
| fabricated levels | 1 | **0** |
| situational grounding | 70% | 80% |

## Tier 1, increment 3 — listwise reranking with the model already loaded

A cross-encoder is the textbook reranker and would have dragged torch back into a
runtime that needs numpy, httpx and orjson. The answering model is already
resident, already knows the domain, and reads twenty-four one-line summaries in
about a tenth of a second. A separate probe had already shown the base model
picks the right excerpt 80% of the time when that is all it has to do, which is
the only thing a reranker is asked for.

Anything the model does not mention keeps its fusion order behind the entries it
did, so a garbled reply degrades to the ranking it was handed.

| recall@8, through the shipped runtime | fusion only | + rerank |
| --- | ---: | ---: |
| hand-written holdout (89) | **84.3%** | 83.1% |
| mined wild questions (300) | 28.7% | **34.7%** |

| end to end, holdout | | |
| --- | ---: | ---: |
| overall | 89.9% | **89.9%** |
| false premise | 94.7% | **100%** (19/19) |
| situational grounding | 80% | 82% |
| descriptive | 75.8% | 72.7% |

**Kept on a split decision, which is worth stating plainly.** Flat on the gate,
minus one item of retrieval recall there, plus eighteen items on the independent
set — well outside its noise — and false premise finally clean. The cost is about
a tenth of a second per query and three points of descriptive accuracy. On by
default; `--no-rerank` turns it off.

`eval/recall_app.py` measures recall through the shipped runtime rather than the
lab implementation, so a retrieval change can be checked at the operating point
before spending four minutes on a full answer run.

## Tier 0, increment 4 — validating the instrument that was driving decisions

Two increments running, the mined set and the hand-written set disagreed about
direction, and I had been trading gate points against the mined one. Before
letting that continue, a recall curve over the whole corpus:

| | R@1 | R@8 | R@50 | R@300 |
| --- | ---: | ---: | ---: | ---: |
| hand-written | 39.3% | 73.0% | 89.9% | **95.5%** |
| mined, raw | 13.3% | 33.3% | 49.7% | **64.0%** |

Nearly every hand-written gold is findable somewhere in 41,743 entries. **A third
of mined golds are not findable at all**, which is what an unanswerable label
looks like, not a hard one.

### Judging the labels

`scripts/validate_wild.py` shows the 27B each question and the full text of the
cited entry and asks whether that entry answers it. The judge never sees a
ranking — filtering by whether *this* retriever can find something would delete
exactly the questions the set exists to expose.

| verdict | pairs |
| --- | ---: |
| ANSWERS | 104 |
| CONTEXT | 238 |
| UNRELATED | 249 |

**The mined set was about 72% noise.** Answers link liberally: "Do Skeletons need
to breathe?" cited a Wyrwood Sneak stat block. 85 of 300 questions have at least
one entry that genuinely answers them; those are `eval/wild_clean.jsonl`.

### Both earlier decisions were right, by much more than the noisy set showed

| recall@8 | raw mined | **cleaned** | hand-written |
| --- | ---: | ---: | ---: |
| narrow only → fused (increment 2) | 22.0 → 31.0 | **38.8 → 56.5** | 82.0 → 83.1 |
| rerank off → on (increment 3) | 28.7 → 34.7 | **49.4 → 58.8** | 84.3 → 83.1 |

Two changes kept on thin or negative evidence from the gate turn out to be worth
+17.7 and +9.4 points on validated real questions. The noise had been diluting
their signal by roughly a factor of two, not inventing it.

### And real questions are simply harder

Cleaned mined recall@8 is **58.8%** against the hand-written set's 84.3%, with
labels now validated on both sides. That gap is not noise and not label quality:
questions people actually ask are harder than the ones I wrote to test myself.

`eval/wild_clean.jsonl` is now a reported metric alongside the gate. It is 85
items, so it advises rather than decides, but it has earned a vote.

## Tier 1, increment 5 — the in-domain embedder, and why the free version fails

Descriptive questions are the remaining retrieval failure, and the pipeline
handles them by writing the summary the answering entry would have and matching
that against a summary index. So the retriever's job is description → entry, and
the corpus ships 38,482 examples of that pairing for free: every entry has its own
one-line summary. No teacher, no generated data.

Trained `Qwen3-Embedding-0.6B` for one epoch on those pairs with cached in-batch
negatives, excluding every benchmark-cited entry. Training loss reached **1.1e-05**
and evaluation loss **4.2e-05**, which was the first sign something was wrong: a
retrieval objective should not be that easy.

**It made retrieval substantially worse on both sets.**

| recall@8 | base | tuned | |
| --- | ---: | ---: | ---: |
| hand-written holdout | **83.1%** | 70.8% | −12.3 |
| validated real questions | **56.5%** | 45.9% | −10.6 |

### The mechanism, which is the useful part

The obvious suspicion is representation collapse. It is the opposite:

| | mean pairwise cosine | sd | p99 |
| --- | ---: | ---: | ---: |
| base | 0.344 | 0.088 | 0.550 |
| tuned | **0.045** | 0.060 | 0.215 |

The tuned model spread the corpus *further apart*, not together. Uniformity
without alignment.

The cause is in the training pair. An entry's one-line summary appears **verbatim
inside the entry text** that serves as its positive, so matching them requires no
paraphrase at all — the anchor is a substring of the target. With nothing to learn
on the positive side, the gradient is dominated by pushing in-batch negatives
apart, and the model duly destroyed the semantic neighbourhood structure that
descriptive retrieval depends on. It got better at telling entries apart and worse
at recognising that a description means one of them.

### What this rules in

The failure is specific and it names its own fix: **positives must be paraphrases
that do not share surface form with the target.** Teacher-written player questions
are exactly that, and are what the roadmap called for before this increment tried
to shortcut it with free data. Hard negatives mined from the retriever's own
confusions would sharpen it further.

Not shipped. Artifacts deleted; the training script stays, since the recipe is
right and only the pairs were wrong.

## Tier 1, increment 6 — the fix worked, the model still lost

Increment 5 diagnosed the failure precisely: an entry's summary appears verbatim
inside its own text, so the training positive contained the anchor and no
paraphrase was ever learned. The fix is free — remove the summary sentence from
the positive.

**The diagnosis was right.** Training loss went from 1.1e-05 to 0.087 and grad
norms from 0.0002 to ~11. The task became non-trivial, exactly as predicted.

**Retrieval improved on the gate:**

| recall | base | v2 (anchor stripped) |
| --- | ---: | ---: |
| holdout R@5 | 76.4% | **82.0%** |
| holdout R@8 | 83.1% | **84.3%** |
| holdout R@20 | 89.9% | **93.3%** |
| holdout MRR | 0.655 | **0.688** |
| wild_clean R@8 | 56.5% | 57.6% |
| wild_clean MRR | **0.345** | 0.306 |

**And end-to-end it lost anyway:**

| | base retriever | v2 retriever |
| --- | ---: | ---: |
| overall | **87.2%** | 84.4% |
| **descriptive** | **72.7%** | 63.6% |
| situational | 100% | 96.9% |
| false premise | 89.5% | 94.7% |

Descriptive questions — the family this was built to fix — got nine points worse
while their retrieval recall got better.

### Recall@k is not the objective

The retriever's job is not to contain the gold entry. It is to assemble eight
excerpts the model can answer from. v2 finds the gold slightly more often and
fills the other seven slots worse — more near-duplicates of the target, fewer
entries that supply the surrounding rules an answer needs. Better on the metric,
worse at the job.

This is worth more than the increment. Every retrieval decision in this project
has been taken on recall@k, and recall@k has now been shown to move in the
opposite direction from answer quality. It stays as a cheap screen, but a change
that clears it still has to face the end-to-end gate before shipping.

Not shipped. Both tuned models deleted; `scripts/train_embedder.py` keeps the
stripping fix.

### What is still untested

Neither run used the pairs the roadmap actually specified: **teacher-written
player questions**, which differ from summaries in register as well as surface
form, plus hard negatives mined from the retriever's own confusions. That remains
the version worth trying, and it now has to beat 87.2% end to end rather than a
recall number.

## Tier 0, increment 7 — what a retrieval "miss" actually is

Increment 6 showed exact-chunk recall can move opposite to answer quality. This
one shows it also miscounts. Reading the 34 misses on validated real questions:

| question | label | retrieved |
| --- | --- | --- |
| Can I have just a striking weapon? | Runes | **Fundamental Runes** |
| Action cost of drawing a weapon? | Wielding Items | **Drawing and Stowing Items** |
| Will uneven speed round up or down? | General Rules | Speed, Round |
| Anything preventing a wizard using a staff of healing? | Casting Spells from a Staff | Staves, Staff of Healing |

Each counts as a miss and each retrieved a page at least as good as the label.
Archives of Nethys rules chapters nest, humans cite whichever level they had
open, and an id match cannot distinguish a failure from a difference of
granularity.

### Asking the question the system is judged on

`eval/answerable_recall.py` shows a judge the question and the excerpts actually
retrieved — never which one was the label — and asks whether they can be answered
from.

| | exact-chunk R@8 | judged YES | judged PART | judged NO |
| --- | ---: | ---: | ---: | ---: |
| hand-written holdout | 84.3% | **56.0%** | 40.4% | 3.7% |
| validated real questions | 60.0% | **11.8%** | 88.2% | 0% |

Two things follow, and the second is the one that matters.

**The judged metric is much stricter than either chunk recall or the end-to-end
score.** The deployed system answers 89.9% of holdout questions while only 56% of
its excerpt sets are judged to contain the answer outright — the model fills the
rest from reasoning and parametric knowledge, and the answer grader accepts a
correct key fact rather than demanding completeness. So 56% and 89.9% are not in
conflict; they measure different things.

**The gap between my questions and real ones is far larger than chunk recall
said: 44 points, not 24.** And it is not explained by question type — a keyword
split finds only 3 of 85 wild questions asking for judgement rather than fact.
The PART bucket is full of ordinary rules lookups:

- "Can I move diagonally across the corner of enemy spaces without tumbling through?"
- "If a player casts a spell of unlimited duration and retrains out of it, does it end?"
- "If trapped by a web lurker, can I only use Acrobatics to Escape?"

These are **interaction and edge-case questions**. Retrieval finds the right
topic and not the specific rule, which is what PART means. My hand-written set
asks almost none of them, because when I sat down to write questions I wrote
lookups — "what level is this feat", "what does this condition do" — and real
players ask what happens when two rules meet.

That is the honest characterisation of the remaining gap, and it is not a
retrieval-breadth problem. More excerpts, multi-hop retrieval over the entity
graph, or ranking within a topic are the directions it points at; a better
embedder is not.

## Tier 1, increment 8 — link expansion, rejected, and a correction to increment 7

Increment 7 said retrieval finds the topic and not the specific rule, and that
those questions are about interactions. A topic page almost always links to the
specific rule involved, and the corpus keeps **394,598 resolved outbound links**
(98% of them, every entry having at least one). So: pull in what the best few
results point at and fuse it as an extra ranking.

Untuned (6 seeds, weight 0.5) it cost the gate 2.7 points. Tuned (3 seeds, weight
0.25) it returned to parity — 89.9%, with situational grounding 80% → 85%.

Then the measurement it was built for:

| judged answerable, validated real questions | |
| --- | ---: |
| without expansion | **31.8%** |
| with expansion | 27.1% |

**Rejected.** Flat on the gate and 4.7 points worse where it was supposed to help.
Links are a weaker relevance signal than they look: a rules page cites everything
adjacent to it, so a blanket one-hop pull adds the neighbourhood rather than the
answer. The code and the packaged graph stay, because multi-hop along a
*reasoned* path is still untried; a blanket walk is not.

### Correcting increment 7

The first expansion measurement looked like a large win — 11.8% → 27.1% — and it
was an artifact. I had run the earlier baseline at `--excerpt-chars 520` and the
new one at 1200, so the judge simply saw more text. Controlled at 1200 the
baseline is **31.8%**, not 11.8%.

That correction lands on increment 7's headline, which used the same mismatched
settings: holdout at 1200, wild at 520.

| judged answerable, matched settings | |
| --- | ---: |
| hand-written holdout | 56.0% |
| validated real questions | **31.8%** |

**The gap is 24 points, not 44.** And it now agrees with exact-chunk recall
(84.3% vs 60.0%, a 24.3-point gap) instead of contradicting it — which is
reassuring about both metrics and was the thing increment 7 got wrong.

What survives from increment 7 is the qualitative finding, which the examples
still support: the PART bucket is interaction and edge-case questions, my
hand-written set asks lookups, and real players ask what happens when two rules
meet. What does not survive is the claim that the two instruments disagreed about
how large that gap is. They never did; I measured them differently.

## Latency: the 60-second answer on a MacBook

Reported from the field: `pf2e serve` on an M-series 16 GB took upwards of a
minute per question, after the warm-start fix had already landed. So this was
per-question inference cost, not cold start.

Nothing in the pipeline was instrumented, which is why "it is slow" had gone
three rounds without a cause. Adding a per-stage timer first turned out to be
the whole job: it named a duplicated stage, a silently disabled one, and the
stage actually worth cutting.

### Bugs the instrumentation found

**The web UI ran retrieval twice.** `/api/ask` called `ask()` and then called
`search()` again to get the hits for the cards, because `ask()` only returned
citation dicts. That is a second rewrite *and* a second listwise rerank on every
question — two extra model calls, roughly a third of the wall clock, for a
ranking that had already been computed. `ask()` now returns its hits and the
server uses them.

**Reranking silently stopped happening.** Splitting the timing out of `search()`
meant calling it with `rerank=False` and reranking in `ask()`. But `search` read
`take = (pool or DEFAULT_POOL) if rerank else k`, so `rerank=False` also
collapsed the candidate pool from 24 to 8 — and `rerank()` returns early when
it is handed fewer candidates than `k`. The pipeline scored the same on the
holdout with reranking disabled, which is its own finding about how much the
holdout can see. Caught by noticing `rerank` missing from the timing output, not
by a score moving.

### What the stages actually cost

Measured on the holdout (109 questions), mean seconds per question on a desktop
GPU. A laptop scales the three model calls up roughly 20×; retrieval, being
numpy over memory-mapped float16, scales far less.

| stage | seconds | what it is |
| --- | ---: | --- |
| rewrite | 0.20 | model call, ~90 tokens out |
| retrieve | 0.54 | BM25 + two dense views + fusion, no model |
| rerank | 0.21 | model call, 24 summaries in, ~60 tokens out |
| answer | 1.20 | model call, ~3.5k tokens of prefill, up to 400 out |

The answer call is the target, and within it the decode. Which is why the
largest change here is not a reduction at all.

### Streaming

The answer is now streamed end to end — Ollama and OpenAI-compatible backends,
the CLI, and the web UI over server-sent events. The total does not change. What
changes is that the sources appear as soon as retrieval finishes and the first
sentence follows immediately after, instead of a blank spinner until the last
token. On the measured desktop, first token lands at 1.1s of a 2.4s answer; the
same ratio on a laptop turns a 60-second blank wait into about 20 seconds to
first text, with the rest arriving at reading speed.

### Swept, and what the holdout could not see

| configuration | holdout |
| --- | ---: |
| 700 answer tokens, 1600 context chars (shipped) | 97/109 (89.0%) |
| **400 answer tokens**, 1600 chars | **98/109 (89.9%)** |
| 400 tokens, 1000 chars | 98/109 (89.9%) |
| 400 tokens, 1600 chars, rerank pool 12 | 97/109 (89.0%) |

All four are one item apart. The honest reading is that this holdout cannot
separate them, not that the differences are zero.

**Taken:** 400 answer tokens. It caps the model's habit of restating the
excerpts as bullets, and costs nothing measurable.

**Then corrected, in use:** a cap does not shorten an answer, it truncates one.
On the M3 laptop the shipped runtime hit the 700 cap on 2 of 30 answers, and at
400 the cut lands mid-sentence and usually before the citation, which is the one
part of the answer a reader can check. "Answer concisely" on its own is ignored
by both 9B and 4B. A concrete budget in the system prompt is not:

| answer prompt | 9B tokens (decode s) | 4B tokens (decode s) | ends on |
| --- | ---: | ---: | --- |
| "answer concisely" (was shipped) | 458 (36.2) | 286 (13.5) | a Source line, after bullets |
| + "under 120 words, answer first, no headings, Source line last" | 156 (11.9) | 155 (7.3) | the Source line |
| + "at most four sentences, then Source" | 139 (10.5) | 111 (5.1) | the Source line |

One question ("How does Treat Wounds work?"), Ollama 0.33.3 on an M3 with 16 GB,
same excerpts each time. The 120-word variant is now the prompt; the four-sentence
one was rejected because it forbids lists, and "list every trait of X" is a real
question shape. The 400 cap stays as a safety net only. Not re-scored on the
holdout yet; the earlier proxy — grading the 4B's answers truncated to 200 tokens
changed no verdict on 31 items — says the graded fact arrives early.

**Not taken:** 1000 context chars, though it scored identically and would cut
prompt processing by a third. 45% of corpus entries are longer than 1000
characters (23% are longer than 1600), so it truncates nearly half the corpus
mid-entry — a real information loss that 109 lookup-shaped questions happen not
to punish. It is exposed as `pf2e serve --context-chars` instead, with the
measurement written down, so the trade is the user's to make on their hardware.

**Not taken:** pool 12. It saves the least of the three and cuts rerank depth,
which is a quality safeguard measured in an earlier increment.

## Model size: how small can the answering model get?

The 9B is the largest single cost in the deployment — 6.6 GB resident and the
slowest stage by far. If a 4B or a 1B held up, the thing would run on machines
it currently does not fit on. `qwen3.5` is the only family in the line with
small variants; 3.6 and 3.8 start at 27B, so this is measured on 3.5 throughout.

### A measurement bug first, because it invalidated the first attempt

The first 4B run took three times as long as the 9B run it was supposed to beat.
Ollama loads at most three models at once (`OLLAMA_MAX_LOADED_MODELS`, default
3). Earlier smoke tests had pinned 9b, 2b and the embedder with a two-hour
keep-alive, so all three slots were taken and the 4B was **loaded and evicted on
every single call** — 10.5 s of `load_duration` per model call, three calls per
question. Nothing errored; it was just silently measuring disk.

The rerun evicts every other LLM before each pass and prints what is resident
before and after, so a repeat announces itself instead of looking like a slow
model.

### Results, 109-question holdout

| model | size | holdout | false premise | decode tok/s | mean s/question |
| --- | ---: | ---: | ---: | ---: | ---: |
| qwen3.5:9b (shipped) | 6.6 GB | **98/109 (89.9%)** | 19/19 | 201 | 2.16 |
| qwen3.5:4b | 3.4 GB | 92/109 (84.4%) | 17/19 | 276 | 1.81 |
| qwen3.5:2b | 2.7 GB | 86/109 (78.9%) | 15/19 | 357 | 1.31 |
| qwen3.5:0.8b | 1.0 GB | 83/109 (76.1%) | 15/19 | 496 | 1.05 |

Decode rates are from a desktop 5090 on the real answer prompt (1440 tokens in,
400 out), cache-busted so prefill is not measuring a cache hit. **The ratios
understate the gain on a laptop**: decode there is memory-bandwidth-bound, so it
tracks weight bytes read per token, and 9b→4b is a 1.9× reduction in bytes
against the 1.37× seen on a GPU that is not bandwidth-starved.

### Where the loss actually is

Splitting each run into "was the answering entry retrieved" and "was the answer
right given that" — the same run files carry both:

| model | gold entry retrieved | correct when it was |
| --- | ---: | ---: |
| 9b | 31.2% | 94.1% |
| 4b | 31.2% | 85.3% |
| 2b | 30.3% | 69.7% |
| 0.8b | 27.5% | 70.0% |

(The absolute retrieval figure is low because it is exact-URL equality and the
remaster hop rewrites URLs; only the comparison between rows is meaningful.)

**At 4B retrieval is untouched — identical to the 9B — and the entire loss is in
answering.** The smaller model rewrites queries and reranks candidates about as
well; it is worse at reading eight excerpts and writing the answer. Below 4B
retrieval degrades too.

### The failure that decides it

The false-premise family asks 19 questions whose premise is a D&D 5e rule that
does not exist in Pathfinder. The 9B gets all 19; the 4B gets 17. Both misses
are the exact failure this project exists to prevent:

> **How many death saving throws do I get before I die?**
> 4B: "You get **three** successful recovery checks (death saving throws) before
> dying."

> **What's my character's proficiency bonus at level 7?**
> 4B: "At level 7, your character's proficiency bonus is **+9**."

Neither concept exists in PF2e. The 9B says so. So the 5.5-point drop is not
spread evenly over harmless questions — it concentrates in confidently answering
a wrong question with the more famous game's rules, which is the worst error a
rules reference can make.

A note on instruments: the refusal regex rates the 4B as refusing *more* often
than the 9B (63% vs 47%), which is backwards. It matches hedging language, and
the 9B mostly does not hedge — it denies flatly ("Pathfinder 2e has no death
saving throws"), which reads as a confident answer. Family accuracy is the
honest measure here; the regex is not.

### Taken

The default stays **qwen3.5:9b**. `--llm-model qwen3.5:4b` is documented as the
real option for a smaller machine — it halves resident memory to 3.4 GB (4.0 GB
with the embedder, against 7.2 GB), roughly doubles laptop decode, and costs 5.5
points concentrated in false-premise questions. That is a reasonable trade for
someone who cannot run the 9B at all, and a bad one for someone who can.

**2B is not worth it.** Its default tag is Q8, so at 2.7 GB it is barely smaller
than the 4B's 3.4 GB while scoring 5.5 points lower again. If something that
size is wanted, `qwen3.5:2b-q4` is ~1.4 GB and untested here.

**0.8B is not usable for this.** It answers a third of false premises with
invented rules and its query rewrites are already fabricating game mechanics
("off-guard ... allows a creature to move freely without being attacked"). It is
fast because it is not doing the job.
