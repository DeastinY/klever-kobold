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
| **Overall** | **92/470** | **19.6%** | |

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
| **Overall** | **108/470** | **23.0%** | |

## Reading

**The contamination premise failed for frontier models.** 60/60 trap questions clean across both
runs. They know the three-action economy, that a natural 20 raises the degree of success rather than
auto-critting, that alignment is gone. This was the stated phase-01 exit criterion and it fired
against the project's own framing. The premise now rests entirely on the open-weight run.

Two caveats before writing it off: the system prompt names the game, which primes correctly — a
fairer test asks "how many attacks can a 5th-level fighter make?" without naming the system. And 30
hand-authored items is a small family. Both are v2 work on the benchmark, not excuses.

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

## Pending

- `Qwen/Qwen3.8-27B` closed-book — the run the premise actually depends on. Weights downloading.
- `Qwen/Qwen3.5-9B` closed-book — to price the iteration cost of the 27B.
