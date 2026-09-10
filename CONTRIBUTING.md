# Contributing

Thanks for wanting to help the kobold get things right. Here is how to do that
without either of us wasting an evening.

## The easiest way to help

**Tell it when it is wrong.** Every answer in the app has a *Wrong? Tell the
kobold* button. A report with the correct ruling and a source is the single most
useful thing you can send, and it takes a minute. What a report contains and
where it goes is in [docs/reporting.md](docs/reporting.md).

**Open an issue** for anything else: a crash, an install that did not work, an
entry that renders badly, an idea. Say what you asked, what you expected, and
what you got. A screenshot of the entries under the answer helps more than a
description of them.

## Running it from a clone

```bash
git clone https://github.com/DeastinY/klever-kobold && cd klever-kobold
uv sync
uv run kobold setup          # Ollama, the two models, the index
uv run kobold serve          # http://localhost:8765
```

`uv run kobold doctor` checks each moving part if something is off. The web page
is one file, `src/kleverkobold/ui.py`, with no build step: edit it, restart, reload.

## Proposing a change

1. **Say what you are going to do first**, in an issue, if it is more than a
   small fix. It saves you building something that is already in progress or
   was tried and dropped.
2. **Branch from `main`, keep the pull request to one thing**, and write the
   description for someone who has not read the code: what was wrong, what you
   changed, how you checked it.
3. **If your change touches how answers are found or written, run the test set
   before and after** and put both numbers in the pull request:

   ```bash
   uv run python eval/run_eval.py --backend app --rerank --benchmark eval/holdout.jsonl --label my-change
   uv run python eval/score.py eval/runs/my-change.jsonl --benchmark eval/holdout.jsonl
   uv run python eval/lore_answers.py     # lore: thirty checkable facts, end to end
   uv run python eval/lore_recall.py      # lore: recall@8, and rules controls that saw the wiki
   ```

   It is 109 hand-written questions and takes about 20 minutes with the default
   model. Differences under four questions are noise, so run it twice if it is
   close, and do not be discouraged by a small loss: say so, and we will look at
   which questions moved.
4. **If you touch the scorer, add a case** to `eval/test_score.py` and run it.

Match the surrounding style. Comments say *why*, especially where a number was
chosen by measurement. Commit messages say what changed and what it was checked
against.

## Things to know before you start

- The **content is not ours.** Rules text is the Archives of Nethys', under the
  ORC License and Paizo's Community Use Policy; both are non-commercial. Read
  [docs/LICENSING.md](docs/LICENSING.md) before publishing anything built from
  this repository, especially model weights.
- **No corpus data is committed.** Everything under `data/` is rebuilt by the
  scripts, and the packaged index ships as a release asset.
- **Fine-tuning has been tried here and lost** to plain retrieval on hand-written
  questions every time. A trained model would need to beat the test set above,
  run more than once, to ship. Retrieval improvements are the more promising
  place to spend an evening.
- **Be kind to the sources.** The build scripts read the Archives of Nethys and
  PathfinderWiki; run them rarely, identify yourself, and never in a loop.

## Where to talk

Issues and pull requests on GitHub. Questions about the game itself belong on
the Archives of Nethys or the Paizo forums, where people know more than the kobold.
