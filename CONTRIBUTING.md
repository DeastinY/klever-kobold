# Contributing

The unusual thing about this project is not the architecture, it is the
measurement discipline. Sixteen measurement bugs have been found here, every one
by reading model outputs rather than model scores, and several ran in the
flattering direction for hours before anyone noticed. Most of the rules below
exist because of a specific one.

## The gate

`eval/holdout.jsonl` — 109 questions written by hand in player language — scored
by `eval/score.py`. **Run it before and after any change and record both numbers,
including when the change loses.** A change that regresses the gate does not
ship, however good the idea was.

```bash
python eval/run_eval.py --backend app --model deployed --benchmark eval/holdout.jsonl \
    --label my-change --retrieve 8
python eval/score.py eval/runs/my-change.jsonl --benchmark eval/holdout.jsonl
```

Report the per-family breakdown, not just the total. Several changes here were
flat overall while moving two families in opposite directions, and that is worth
knowing before you ship one.

## The other instruments

| set | n | labels | role |
| --- | ---: | --- | --- |
| `eval/holdout.jsonl` | 109 | hand-written | **the gate** |
| `eval/wild_clean.jsonl` | 85 | mined from RPG StackExchange, judge-validated | advisory, and has earned a vote |
| `eval/wild.jsonl` | 300 | mined, raw | superset; ~72% label noise, kept for provenance |
| `eval/benchmark.jsonl` | 459 | generated | continuity only; names its target in 88% of questions |

Cheap screens, in order of cost: `eval/recall_app.py` (~70 s, recall through the
shipped runtime), `eval/answerable_recall.py` (~5 min, judged), full end-to-end
(~4 min per set).

**Do not decide on recall@k alone.** It has been shown here to move in the
opposite direction from answer quality — an embedder that improved recall on
every k made end-to-end answers three points worse. Recall is a screen; the gate
is the decision.

## Rules that exist because something went wrong

- **An implausible number is a bug until proven otherwise.** Sixteen for sixteen.
  A retrieval loss of 1e-05, a 25% score that should have been 70%, a metric that
  doubled when an unrelated flag changed — every one was a defect, never a
  discovery.
- **Read the outputs.** Every measurement bug here was found that way and none
  was found by a failing test.
- **Change one thing per measurement.** One reported result was inflated from 24
  points to 44 because two runs used different `--excerpt-chars`. It survived
  into a headline before being caught.
- **Measure at the operating point.** The system retrieves 8 excerpts; retrieval
  decisions were gated at recall@5 for six increments before anyone noticed.
- **If you touch `eval/score.py`, add a case to `eval/test_score.py`** and run it.
  43 cases, most taken verbatim from real runs, including negatives that must
  *not* match.

```bash
python eval/test_score.py
```

## Fine-tunes

Three have been trained here and none shipped. Two improved a benchmark generated
by the same pipeline that produced their training data and lost on questions
written by hand. **A fine-tune ships only if it wins on hand-written questions**,
and the burden is on the adapter.

If you train one, exclude every benchmark-cited entity from generation and verify
the exclusion — `scripts/make_raft_data.py` shows the checks, and one run had to
be restarted at step 18 because 25 entities leaked.

## Style

Match the surrounding code. Comments explain *why*, especially where a value was
chosen by experiment — `DEFAULT_K = 8` carries the sweep that produced it, and
that is the house style, not decoration.

Commit messages say what was measured and what failed. The log is the experiment
record; `notes/experiments.md` is its long form.

## Corpus and licensing

Nothing derived is committed; the corpus rebuilds from four scripts. Rules
mechanics are ORC-licensed and Golarion lore is under Paizo's Community Use
Policy — non-commercial, freely available use only. See
[`docs/LICENSING.md`](docs/LICENSING.md) before publishing anything built from
this, especially model weights.

## Wrong-answer reports

The **Wrong? Report it** button in the web UI sends reports to the project
mailbox (what is sent and why: the README's "Reporting wrong answers" section).
The intended path for a confirmed report is a new holdout question: add it to
`eval/seeds/natural_holdout.jsonl` in the same shape as its neighbours, with the
corrected ruling as the gold and the Archives entry as the ref, rewritten in your
own words and with nothing that identifies the reporter. Then it is measured on
every change.
