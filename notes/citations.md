# Do the models cite, and do they cite correctly?

Measured from cached retrieval runs, k=5 excerpts. "Correct source" means the response contains the
URL of a gold chunk; "never retrieved" means it contains an AoN URL that was not among the five
excerpts supplied.

| Model | cites | correct source | wrong source | never retrieved |
| --- | ---: | ---: | ---: | ---: |
| gpt-5 | 98.3% | **86.4%** | 1.9% | 0.5% |
| gpt-4.1-mini | 95.2% | 82.8% | 3.6% | 0.5% |
| Qwen3.5-9B | 97.9% | 82.6% | 4.8% | 2.1% |
| Qwen3.8-27B | 90.7% | 81.6% | 1.2% | 0.7% |

**Citation is not a problem.** Every model cites nearly always, cites the correct source at
essentially the same rate as it answers correctly, and almost never invents a URL. Forcing citation
would buy roughly nothing on answerable questions.

## The abstention row is a different story

On the 40 questions about feats that do not exist:

| Model | cites a source anyway | cites a URL never retrieved |
| --- | ---: | ---: |
| Qwen3.5-9B | **90.0%** | 7.5% |
| gpt-5 | 52.5% | 0.0% |
| gpt-4.1-mini | 22.5% | 0.0% |
| Qwen3.8-27B | 20.0% | 0.0% |

The 9B answers a question about a feat that was never written, and attaches a real citation to a
*neighbouring* feat, nine times out of ten. The citation is what makes the answer persuasive. That
is the failure worth attacking, and it is not fixed by demanding citations — it is fixed by removing
the option to cite something irrelevant.

## What that implies

Forcing citation *format* is solved already. Forcing citation *from a closed set that includes
"none of these"* is a different intervention: it turns abstention from a behaviour the model has to
volunteer into a classification it is forced to make. `eval/selection_probe.py` measures exactly
that — it reads the logits for the six tokens `1 2 3 4 5 N` and nothing else, so nothing can be
generated and nothing can be hallucinated.

This is worth running as a third arm alongside the LoRA, because it costs one forward pass per item
and no training at all.
