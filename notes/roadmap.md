# Roadmap

State as of 2026-09-07: the deployed runtime answers **89.0%** of 109 hand-written
questions, on a 16 GB laptop, in 1.6 s, citing Archives of Nethys.

Everything below is ordered by where the remaining errors actually are, not by
what is interesting to build.

---

## Where the 12 remaining failures live

| | count | |
| --- | ---: | --- |
| Retrieval missed the entry, descriptive questions | **8** | the answer was never in the context |
| Model had the entry and answered wrong | 3 | 2 legacy naming, 1 descriptive |
| Genuine abstention failure | 1 | declines the wrong question |

**Two thirds of the remaining headroom is descriptive retrieval.** Every failing
question describes something the corpus contains — "a way to patch up an ally
mid-fight", "the cantrip most casters take for reliable damage", "the item you
need to pick locks" — and the right entry never reaches the context window.

---

## Tier 0 — the instrument, before anything else

12 failures across 109 items means **one item is 0.9%**. Nothing below can be
told apart from noise at that resolution, and the project's history is a long
list of measurement bugs found by reading outputs (twelve of them, the largest
worth 15 points).

1. **Grow the holdout to 300+.** Non-negotiable prerequisite for tuning.
2. **Stop writing the questions myself.** Mine real ones — r/Pathfinder2e, the
   PF2e Discord rules channels, Paizo forum threads. My questions share my blind
   spots by construction, which is exactly the failure mode the first benchmark
   had.
3. **Cross-check the scorer against a judge.** Sample 60 graded items, have a
   frontier model grade them independently, and read every disagreement. That is
   how bug thirteen gets found before it flatters a headline for a week.
4. **Split dev and test.** Everything so far has been tuned on the set it is
   reported on. A frozen test half, opened rarely, would make the numbers mean
   what they appear to mean.

*Effort: a day. Gate for everything else.*

---

## Tier 1 — descriptive retrieval (8 of 12 failures)

Recall@5 is 76.4% overall but the descriptive family carries almost all the loss.
Four things to try, cheapest first, each measured alone:

1. **A reranker over the top 50.** The pipeline fuses four rankings and then
   truncates; nothing ever re-reads the candidates against the question. A small
   cross-encoder is the standard fix and the obvious first move.
2. **Train the embedder in-domain, properly.** Generate (question, entry) pairs
   from the corpus with the 27B and fine-tune `Qwen3-Embedding-0.6B` on them.
   The one published PF2e embedder turned out to be numerically identical to its
   base, so this is genuinely unexplored — and it is the component that most
   directly determines descriptive recall.
3. **Multiple hypothetical summaries.** One generated summary is one sample from
   a distribution; three, fused, cover more of it. Cheap: the rewriter already
   runs.
4. **Ask twice.** When the top result's score is low, re-rewrite with the first
   attempt's misses visible and search again. Latency cost only on hard queries.

*Expected: R@5 76% → 85%+, worth roughly 5 points end to end.*

---

## Tier 2 — coverage and freshness

1. **Index the lore.** 22,604 PathfinderWiki chunks are built and unused by the
   deployed system, which answers rules questions only. Golarion questions are
   half of what a GM asks. Needs a source filter so lore never answers a rules
   question.
2. **Structured queries deserve a structured path.** "Level 4 fighter feats with
   the flourish trait" is a database filter wearing a question's clothes; running
   it through semantic search is strictly worse than a `WHERE` clause. The
   metadata is already in the index.
3. **Errata.** Archives of Nethys changes continuously. A monthly re-dump,
   re-embed and re-release, with the holdout run before publishing, keeps the
   index from quietly rotting.

---

## Tier 3 — the thing people actually use

1. **Follow-up questions.** Every real rules conversation is multi-turn ("what
   about if she's prone?"). Today each question is independent, which is the
   single most obvious gap between this and a usable assistant.
2. **Character context.** Import a Pathbuilder JSON and filter answers to what
   *this* character can actually take. Turns a rules lookup into advice.
3. **Foundry VTT module.** `foundryvtt/pf2e` is Apache-2.0 and officially
   partnered with Paizo; it is where these questions get asked.
4. **Streaming output.** 1.6 s to first token feels slower than it is.

---

## Tier 4 — the model (deliberately last)

The evidence says this is the least valuable direction, and it took two adapters
to establish that:

- The RAFT adapter scored **+10 on a generated benchmark and −3 on hand-written
  questions**. It learned a question shape, not the domain.
- The abstention adapter was abandoned when its target family turned out to be a
  grading artifact — 73.7% measured, 94.7% real, one genuine failure left.
- The teacher refuses only 2 times in 31 on false premises, so there is nothing
  to distil, and RefusalBench finds the same across thirty models.

What would change the calculus:

1. **Distil the rewriter.** The 27B rewrites queries 6 points better than the 9B,
   and rewriting is a narrow, verifiable task with abundant training pairs — the
   opposite of the open-ended answering task the adapters failed at. This is the
   one fine-tune the data currently supports.
2. **A small Qwen 3.6/3.8.** Neither family ships below 27B today. If a 4–9B
   appears, re-run the model sweep; it is an afternoon.
3. **Retrain only on mined natural questions**, never on templates, and only
   after Tier 0.

---

## Standing rules

- **Every change is measured on hand-written questions before it ships.** The
  generated benchmark is kept for continuity and is not the deciding number.
- **An implausible number is a bug until proven otherwise.** Twelve for twelve so
  far.
- **Read the outputs, not the scores.** Every single measurement bug in this
  project was found that way, and none were found by a failing test.
- **Add a case to `eval/test_score.py` whenever the grader changes.** 43 and
  counting.
