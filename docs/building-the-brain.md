# Building the brain

The nerdy part: how the kobold finds and writes an answer, what was measured,
what fine-tuning did and did not do, and how to rebuild everything from source.
The complete record, including every failed attempt and the measurement bugs
found in our own favour, is [`notes/experiments.md`](../notes/experiments.md).

## RAG, not a fine-tune

That was the first finding and it survived every attempt to overturn it. A
QLoRA/RAFT fine-tune of the answering model scored +10.1 on the generated
benchmark and **−7.0 on hand-written questions**: better at the benchmark's
tics, worse at the job. Fine-tuning the embedder was tried twice and rejected
twice; the second attempt improved recall at every *k* while end-to-end accuracy
fell, which is the single most useful thing this project learned about metrics.
The runtime therefore carries no trained weights of its own: an off-the-shelf
embedder, an off-the-shelf answering model, and everything in between is
retrieval engineering.

## Retrieval

BM25 + dense over full text + dense over a one-line summary index, fused by
reciprocal rank fusion (smoothing 5, not the TREC default 60; swept). On top:

- a **rewrite** step that has the model write the one-line summary an answering
  entry *would* have, and matches that against the summary index;
- **category routing** fused with the unrouted ranking rather than replacing it;
- a **legacy → Remaster hop**, so the pre-Remaster name still finds the current entry;
- **canonical collapse** before fusion, so an entity's evidence is pooled across
  its printings, with the best-ranked printing served (the oldest printing was
  served for a while, which was half of every excerpt set; fixed);
- a **listwise rerank** of 24 candidates down to 8 using the answering model, so
  there is no cross-encoder and no torch;
- the entry the question **names goes last** in the prompt, next to the
  question, because small models read the end of a long context and skip the
  start. "What level is Gurglegut?" with Gurglegut as excerpt one got "no such
  creature" every time; as excerpt eight it got "level 12" every time.

Natural-phrasing recall went 47.2% → 76.4% R@5; situational questions 7.7% → 77.4%.

## The answer

The model gets the eight entries, 1,600 characters each, and a system prompt
with a 120-word budget and a Source line last. The budget matters more than it
looks: told only to "answer concisely" the 9B wrote 458 tokens, which is 37 s of
a 52 s answer on a laptop; given the budget it wrote 156 and still ended on the
citation. A token cap is kept as a safety net only, because a cap that bites
cuts mid-sentence and usually before the Source line.

After the answer, the server scans it for names of rules entries and sends
those entries along, so the page can link "Grab an Edge" to Grab an Edge.

## Model choice

All on the 109-question hand-written holdout through the deployed runtime, on index-v2:

| model | resident | holdout |
| --- | ---: | ---: |
| qwen3.5:9b | 6.6 GB | **100/109 (91.7%)** |
| qwen3.8:27b | 17.7 GB | 98/109 (89.9%) |
| **qwen3.5:4b** *(default)* | 3.4 GB | 93/109 (85.3%) |
| qwen3.5:2b | 2.7 GB | 86/109 (78.9%) |
| qwen3.5:0.8b | 1.0 GB | 83/109 (76.1%) |

Nothing above 9B is worth its memory: 27B is 2.8× the weights for no gain. The
ceiling is retrieval, not the answering model. The 4B is the default because
its seven-item gap is not felt in use and its speed is felt on every question:
on an M3 it decodes at 22 tokens/s against the 9B's 12, and a 16 GB laptop stays
usable while it thinks. A 31-item subset once showed the 4B *ahead* of the 9B;
over all 109 the 9B wins by seven. Subsets that small cannot rank models here.

**Against frontier models**, same retrieval, on the generated benchmark:
qwen3.5:9b **89.5%**, gpt-5 **88.0%**, gpt-4.1-mini 82.4%. Closed-book, gpt-5
scores **27.9%**. The corpus is doing nearly all the work, which is the point.

## Measurement discipline

- The gate is 109 hand-written questions in player language, graded
  deterministically by string matching; no LLM judge is involved in any
  headline number.
- **The noise floor is ±3 items.** One configuration run three times scored
  95, 93, 92: Ollama is not reproducible across processes even at temperature 0.
  Differences under about four items are not results, and two claims were
  retracted for exactly this.
- Sixteen measurement bugs have been found, every one by reading model outputs
  rather than scores. [`CONTRIBUTING.md`](../CONTRIBUTING.md) is mostly the rules
  that came out of them.

## Known weaknesses

- **Rule interactions are unreliable.** The headline number is lookups. On 85
  real questions mined from RPG StackExchange, only 31.8% of retrieved excerpt
  sets are judged to contain the answer outright.
- **Lore is not indexed.** 22,604 PathfinderWiki chunks are built and unused.
- **No multi-turn.** Every question starts cold.
- **Pages that AoN renders from tables** (a rules page's activities, a chapter's
  key terms, a creature's abilities) lost their lists in index-v1 and v2. The
  normalizer now resolves those embeds; it lands with the next index.
- **Renames the Archives do not label.** Force Barrage carries no legacy name on
  the site, so "Was Magic Missile renamed?" fails on index-v2. The next build
  fills legacy names in from the legacy entry and writes "Formerly Magic
  Missile" into the text.
- **`follow_remaster` resolves hop targets under the wrong category** for class
  features. Left alone deliberately: the targets are class pages, and a working
  hop would serve a whole class in place of a feature. Needs measuring, not patching.

## The corpus

| Source | Entries | Licence | Fetched by |
| --- | ---: | --- | --- |
| [Archives of Nethys](https://2e.aonprd.com/) | 41,743 | ORC / Paizo CUP | `scripts/dump_aon.py`, from the Elasticsearch index behind the site's search |
| [PathfinderWiki](https://pathfinderwiki.com/) | 22,604 *(unused)* | Paizo CUP | `scripts/dump_wiki.py`, MediaWiki API, rate-limited |

Nothing derived is committed. The packaged index (metadata, bodies, two float16
embedding matrices, BM25, a link graph, a manifest with an embedder fingerprint)
ships as a [release asset](https://github.com/DeastinY/klever-kobold/releases).
`src/kleverkobold` is the runtime; `scripts/` builds; `eval/` measures; `notes/`
records. When and how external sources are read, and what that means legally,
is in [LICENSING.md](LICENSING.md).

## Rebuilding the index

On a machine with a GPU (the two embedding passes are the slow part):

```bash
scripts/rebuild_index.sh
```

That runs dump → chunks → embed (full and summary views) → package, and fails
on any feature the runtime shows going missing: resolved embeds, links kept,
legacy names filled, whole bodies. Then:

```bash
tar czf kobold-index.tar.gz -C dist kobold-index
gh release create index-vN kobold-index.tar.gz --title "Packaged index vN"
```

and point `INDEX_URL` in `src/kleverkobold/app.py` at the new tag. Re-score the
holdout on the new index before publishing; the recipe is in `CONTRIBUTING.md`.

## Training data, if it comes to that

Wrong-answer reports ([reporting.md](reporting.md)) carry question, wrong answer,
correction and source: the shape of a preference pair. If enough accumulate they
become a fine-tuning set. Given the RAFT result above, the bar for shipping any
trained weights is a clear win on the hand-written holdout, run more than once.
