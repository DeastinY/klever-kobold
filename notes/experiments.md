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

## Targets for phase 03

The LoRA has to move these, without regressing the recall families:

| Metric | Qwen3.8-27B | Qwen3.5-9B | gpt-5 |
| --- | ---: | ---: | ---: |
| `trap_5e` clean | 83.3% | 70.0% | 100% |
| `trap_5e_applied` clean | 81.2% | 68.8% | 93.8% |
| applied grounding | 36% | 9% | 78% |
| `abstention` | 77.5% | 27.5% | 77.5% |

The 9B is the better development target: 2.5x faster to evaluate, and with twice the contamination
and a quarter the grounding it has far more headroom to demonstrate the adapter is doing anything.
Prove it there, then port to the 27B.

## Pending

- Retrieval-augmented reruns of all four, which is the number that actually decides the project.
