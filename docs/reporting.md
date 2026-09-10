# Reporting wrong answers

The measured weakness of the kobold is that it answers rule interactions wrongly
while sounding sure. The 109 hand-written questions catch some of that; the
questions real tables ask catch the rest, and the only way to collect those is to
ask. Every finished answer carries a **Wrong? Report it** button.

## What a report contains

The question, the answer exactly as shown, what you typed as the correction, an
optional source (an Archives URL or a page number), the names and URLs of the
eight entries the answer was built from, the answering model, the index version,
and the app name. That is the whole list.

Not sent: your settings, your history, your favourites, any API key, anything
you did not type into that form. A hash of the sender's IP is kept for a
20-a-day-per-person limit and for nothing else.

## Where it goes

To a small mailbox the maintainer runs on Cloudflare Workers,
`https://kobold-reports.deastiny.workers.dev`, backed by a D1 table. The code is
in [`deploy/report-worker`](../deploy/report-worker/README.md); anyone can run
their own with six commands and point the app at it with `--report-url`.

Nothing is sent unless someone fills the form in and presses Send. The kobold
otherwise makes no network calls after setup, and this stays true.

If you would rather your report went into a GitHub issue under your own name,
run with `--report-url ''`: the same button then opens a pre-filled issue.

## What we do with them

Reports are the raw material for making the thing better, in this order:

1. **Regression cases.** A confirmed wrong answer becomes a hand-written holdout
   question with the corrected answer as its gold, so it is measured on every
   change from then on
   ([`eval/seeds/natural_holdout.jsonl`](../eval/seeds/natural_holdout.jsonl)).
2. **Retrieval and prompt fixes.** Most wrong answers so far were the right entry
   not being retrieved, or being retrieved and ignored. Reports show which of the
   two it was, because they carry the entries used.
3. **Index defects.** A page that lost its list, a rename the index does not
   know, a legacy entry served as current: reports point at the entry, the build
   gets fixed, the index gets rebuilt.
4. **Training data, eventually.** Question, wrong answer, correction and source
   is the shape of a preference pair. If enough accumulate they become a
   fine-tuning set, written up in [`notes/experiments.md`](../notes/experiments.md)
   when it happens.

Reports are not published as they arrive. Corrections that turn into holdout
questions are rewritten in the maintainer's words, without anything that could
identify the reporter.
