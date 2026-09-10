# Follow-up questions

Roadmap Tier 3, item 1. Today every question is independent, and a real rules
conversation is not:

> How does Treat Wounds work?
> — what if she's untrained?
> — and how long before trying again?

The interesting part is not the interface. It is that retrieval here is
entirely query-driven: four rankings fused, three of them keyed on the question
text and the fourth on a summary generated from it. "what if she's untrained?"
is three stopwords and a pronoun. BM25 has nothing to match, the dense views
land on whatever "untrained" means in the abstract, and the eight excerpts that
reach the model are about proficiency ranks in general. Measured, off the shelf:

```
what if she's untrained?
  Untrained Improvisation · Uncommon · Skill Actions · Skill Training ·
  Clever Improviser · Skill · Skilled Human · Training
```

Treat Wounds is not in there, so no answering model — local, frontier, or
otherwise — can get this right. The feature is a retrieval problem wearing a
chat interface.

---

## What was considered

| | | |
| --- | --- | --- |
| **1. Concatenate.** Search on the previous question plus the new one. | free | The old question's terms outvote the new one's. "How does Treat Wounds work? what if she's untrained?" retrieves Treat Wounds again and answers turn one a second time. It is also wrong in the other direction: after two turns about grabbing, a genuine change of subject drags the old topic along. |
| **2. Carry the excerpts forward.** Skip retrieval; re-use the previous turn's eight entries. | free, and instant | Works only while the follow-up stays inside the topic. "and what about Battle Medicine?" needs an entry that was never retrieved, and there is no signal that says which case you are in. It also breaks the citation contract: the model would keep citing entries the current question never matched. |
| **3. Union the excerpts.** Re-retrieve *and* keep the previous eight. | one extra model call | k was swept end to end and the curve is an inverted U: 5 → 81.7%, 8 → 85.3%, 12 → 80.7%. Sixteen excerpts is on the far side of that. Paying a measured accuracy loss to keep entries the new question can retrieve for itself is a bad trade. |
| **4. Fold the history into the rewriter.** The rewrite call already runs; give it the previous turn and one more output line. | free | Tempting, and rejected for one reason: it would change `REWRITE_SYSTEM`, which is the prompt every number in this repository was measured with. It also entangles two failures — a bad summary and a bad de-referencing become one garbled reply that nobody can attribute. |
| **5. Condense, then run the existing pipeline unchanged.** One short call turns the follow-up into a question that stands on its own; everything downstream sees only that. | one extra model call | Chosen. |

## What was built

A **condense** stage in front of the pipeline, and nothing else changed.

```
follow-up ──▶ condense ──▶ standalone question ──▶ rewrite ──▶ retrieve ──▶ rerank ──▶ answer
                  ▲                                                                      ▲
            previous turn                                                        previous turn
```

Four things make this the cheap version of the idea:

**One job per call.** The condenser produces one line and is given the label to
put in front of it. When a follow-up goes wrong you read one short string and
know immediately whether the kobold misunderstood the question or merely failed
to find it. That line is printed by `kobold chat`, shown on the page, and
returned on the `sources` event, because the project's standing rule is that
every measurement bug so far was found by reading outputs.

**Failure is free.** Empty reply, an essay instead of a question, a backend that
falls over mid-call — every one of them returns the question exactly as typed,
which is today's behaviour. There is no state in which turning the switch on is
worse than leaving it off, except by the cost of the call. Eleven shapes of bad
reply are cases in `eval/test_followup.py`.

**One turn travels, and it carries its own condensed form.** A `Turn` holds the
question, the answer, and the standalone question the last condense produced.
Turn three is condensed against turn two's *standalone* form — a question that
already names its subject — so a chain repairs itself one link at a time
instead of growing a transcript in the prompt. Measured working three deep:
"How does Treat Wounds work?" → "what if she's untrained?" → "and how long do
we have to wait before trying again?" condenses to "How long must a character
wait before attempting Treat Wounds again?" with only turn two in view.

**The excerpts are re-retrieved every turn, and citations never cross turns.**
The previous turn's *text* is in the answering prompt; its excerpts and its
URLs are not. So every URL in a `Source:` line is an excerpt the model could
see on this turn. `notes/citations.md` measured the failure this avoids: the 9B
attaches a real citation to a neighbouring entry nine times out of ten on
questions it should decline, and the citation is what makes the wrong answer
persuasive. Letting a model cite a page it can no longer read would manufacture
that failure on purpose.

### Two details that are easy to get wrong

The conversation block goes **before** the excerpts, not between them and the
question. `named_last` exists because the 4B answered "no such creature exists"
about a creature sitting in excerpt [1] and answered correctly when the same
entry was moved to excerpt [8], next to the question. A conversation block
wedged in there would undo an effect worth that much. A follow-up prompt is
therefore the single-turn prompt with a block prepended, and the single-turn
prompt is byte-identical to what it was — asserted, as a byte comparison, in
the tests.

`named_last` also starts working on follow-ups for free, and this was not
planned. It moves entries the question names by name to the end of the
excerpts; "what level is it?" names nothing, but "What level is Battle
Medicine?" does.

## How to turn it on

**Off everywhere by default.** With no history the pipeline makes no extra
call, the prompt is unchanged to the byte, and the system string is unchanged
to the byte.

| Surface | Switch |
| --- | --- |
| Python | `Assistant.ask(q, history=[Turn(question=…, answer=…, standalone=…)])`. Also on `ask_stream` and `retrieve`. `history=None` is off. |
| CLI | `kobold chat` — a conversation, one turn at a time. `/new` drops the thread. `kobold ask` is untouched and stays one-shot. |
| HTTP | `/api/ask` and `/api/search` take `followup=1` plus `prev_q`, `prev_a`, `prev_std`. Without `followup=1` the other three are ignored entirely. |
| Web UI | Settings → Expert mode → Conversation → **Follow-up questions**. Off by default, and not part of either preset: it is a mode, not a quality knob. |
| MCP | Nothing. See below. |

The server keeps no session, no cookie and nothing between requests: the page
holds the conversation and sends one turn with the next question, which is the
same bargain the history panel already makes.

**MCP deliberately gets nothing.** `kobold_ask`'s caller is Claude, which
already holds the transcript and condenses better than a 4B ever will. The
right thing for that caller to do is ask a standalone question, which it can
already do. Adding a parameter would be a worse condenser wrapped in an API.

## What it costs

Every timing below is from one desktop with an RTX 5090 and a Ryzen 7800X3D.
**That is not a laptop**, and the roadmap's 1.6 s is. Absolute seconds here mean
nothing about the machines this runs on, so what is reported is the ratio and
the token counts, which travel.

### Tokens (from Ollama's own `prompt_eval_count`, n=7)

| | tokens |
| --- | --- |
| Condense call, prompt | median **522**, range 445–567 |
| Condense call, output | median **12**, max 23 |
| Answering prompt, single turn | median 1,768 |
| Answering prompt, growth from the earlier turn | median **+190 (12.3%)**, max +237 (14.3%) |

Most of the condense prompt is its own few-shot system string, which is a
fixed 329 tokens of the median 522. That is the obvious thing to shrink if this
ever needs to be cheaper.

### Latency: a follow-up costs about a sixth of an answer

| condition | condense | the call it is compared with | share |
| --- | ---: | ---: | ---: |
| Both models GPU-resident, whole pipeline (n=7) | 0.12 s median | 1.67 s, the whole follow-up | 7.6% |
| GPU, the two calls alone | 0.09 s | 0.63 s, the answer call | 14% |
| **Same machine, `num_gpu: 0`**, the two calls alone | 4.32 s | 24.24 s, the answer call | 18% |
| Same machine, CPU-only, whole pipeline through `kobold chat` | 4.5 s, 5.7 s | 41.7 s, 42.5 s totals | 11–13% |
| GPU under load from another job, through the HTTP endpoint (n=10) | 1.00 s median | 6.72 s median total | 15% |

Five conditions spanning two orders of magnitude in absolute speed agree on
14–18% of an answer call, and 8–15% of a whole question. The condense call is
short input, short output, and it scales like everything else on the machine.
On a laptop where an answer takes fifteen seconds, expect roughly two more.

### Memory: nothing

No new array, no new model, no cache, no session store. The server's resident
set over ten consecutive follow-ups:

```
RSS before 51.2 MB, after ten follow-ups 51.2 MB (delta +0.0 MB)
```

On the model server one follow-up puts about 190 more tokens through one
request, transiently. The 6 GB budget is not touched: the two models and the
250 MB of memory-mapped index are exactly what they were.

---

## Evidence

### Retrieval: 2/14 → 13/14, and that is a smoke test, not a benchmark

`eval/followup_probe.py` — ten threads, fourteen follow-ups, each labelled with
the entries that would have to be retrieved for an answer to be possible. It
measures retrieval only, at k=8, rerank off, which is the shipped 4B's setting.
It also runs the *harder* arm for the feature: the probe never answers, so the
condenser sees only the previous question and never a previous answer, which is
where the entity names are thickest.

```
14 follow-ups across 10 threads, k=8, rerank=off, no previous answer carried
  switch off:  2/14
  switch on:   13/14
```

**Fourteen items written by the person who wrote the feature is exactly the
failure mode Tier 0 of the roadmap exists to fix**, and this number does not go
in a README. What it is good for is that the off arm is 2/14 — the feature is
not competing with a working baseline, it is competing with nothing — and that
the thirteen fixes are visible one by one. Two examples, verbatim:

```
  FIXED  can I still cast spells?
           read as: 'Can a grabbed creature still cast spells?'
           off: Divine Spellcasting · Sorcerer Spellcasting · Witch Spellcasting ·
                Basic Spellcasting · Arcane Spellcasting · Signature Spells ·
                Cleric Spellcasting · Basic Magus Spellcasting
           on : Grabbed · Grab · Improved Grab, Improved Knockdown, or Improved Push ·
                Grasping Earth · Casting Spells from a Wand · Spells · Restrained ·
                Casting Spells from a Staff

  FIXED  what level is it?                       [after "How does Battle Medicine work?"]
           read as: 'What level is Battle Medicine?'
           off: Level · Level-Based DCs · Item Level · Skill Increases ·
                Different Item Levels · Determining Level and Price · Leveling Up ·
                Non-Combat Level
           on : Battle Hardened · Battle Medicine · Paragon Battle Medicine ·
                Warfare Expertise · Debilitating Strike · Communal Healing ·
                Godless Healing · Field Medic
```

### The one that failed, and why it is not this feature's fault

```
  neither  what happens when I block with it?    [after "How does Raise a Shield work?"]
           read as: 'What happens when a character blocks with a raised shield?'
           want any of ['Raise a Shield', 'Shield Block']
           off: Swift Block Cabochon · Intercept Attack · Disarming Block · Rebound Fulu ·
                Implements Interruption · Disarming Intercept · Destructive Block ·
                Aggressive Block
           on : Hostile · Off-Guard · Unfriendly · Shield Warden · Restrained ·
                Helpful · Shields · Prone
```

The condensation is correct. "What happens when a character blocks with a
raised shield?" is a good question, and retrieval still cannot find Shield
Block from it — the rewriter's kind guess sends it into conditions. That is a
descriptive-retrieval miss, which is Tier 1 of the roadmap and eight of the
twelve remaining holdout failures. Condensation hands the existing retriever a
fair question; it does not make the retriever better than it is.

### End to end, on the 4B

Five conversations run through `Assistant.ask`, each follow-up also run with
the switch off. Verbatim, trimmed only where marked.

**Thread 1.**

```
you > How does Treat Wounds work?
kobold> Treat Wounds requires a healer's toolkit and takes 10 minutes to treat one
living creature, granting temporary immunity for 1 hour. The base DC is 15, yielding
2d8 HP on success. Higher proficiency ranks allow attempting higher DCs (Expert 20,
Master 30, Legendary 40) to gain bonus healing (+10, +30, or +50 HP). […]
Source: https://2e.aonprd.com/Actions.aspx?ID=2399

you > what if she's untrained?
  (read as: What happens when a character untrained in Medicine attempts Treat Wounds?)
kobold> If the character is untrained in Medicine, they cannot perform the Treat
Wounds action. […] There is no information in the excerpts regarding how an untrained
character attempts to treat wounds or what damage they might deal on a failure.
Source: https://2e.aonprd.com/Actions.aspx?ID=2399

        [switch off, same question]
kobold> If a character is untrained in a skill, they can only perform that skill's
"untrained actions" […] feats like Untrained Improvisation (level 3) can increase
this bonus to level minus 2 […]
Source: https://2e.aonprd.com/Rules.aspx?ID=2136

you > and how long do we have to wait before trying again?
  (read as: How long must a character wait before attempting Treat Wounds again?)
kobold> You can treat a patient once per hour. […] a patient cannot be treated again
until the full hour has passed since the last treatment began.
Source: https://2e.aonprd.com/Actions.aspx?ID=2399

        [switch off, same question]
kobold> The waiting period depends entirely on which specific ability you are using.
For the *Treat Disease* action […] For the *Escape* action […] The *Rule of Three*
feat […]
```

Turn three is the point of the design. Only turn two was in view, and turn two's
own condensed form still said "Treat Wounds".

**Thread 2, three deep, changing what the question is about.**

```
you > What does the grabbed condition do?
kobold> The grabbed condition means you are held in place by another creature, granting
you both the off-guard and immobilized conditions. If you attempt a manipulate action
while grabbed, you must succeed at a DC 5 flat check or lose the action […]

you > can I still cast spells?
  (read as: Can a grabbed creature still cast spells?)
        [switch off: eight class spellcasting entries, and an answer about spell slots]

you > what about a spell with a somatic component?
  (read as: What happens when a creature with the Grabbed condition tries to cast a
             spell that has a somatic component?)
kobold> You cannot cast spells with somatic components if you are restrained […] While
the grabbed condition only restricts attack and manipulate actions unless specified
otherwise, it does not inherently prevent spellcasting. […]
Source: https://2e.aonprd.com/Conditions.aspx?ID=90
        https://2e.aonprd.com/Rules.aspx?ID=283
```

**Thread 4, where the follow-up refers to something by description.**

```
you > How does Battle Medicine work?
you > how does that differ from the one that takes ten minutes?
  (read as: How does Battle Medicine differ from Treat Wounds?)
kobold> Battle Medicine is a single-action feat allowing you to restore hit points and
reduce conditions like sickened or enfeebled immediately, without removing the wounded
condition. […] In contrast, the standard Treat Wounds action […] typically takes ten
minutes […]

        [switch off, same question]
kobold> The excerpt provided does not contain information about a specific action or
feat that differs from an activity taking ten minutes […]
```

"the one that takes ten minutes" was never named in the conversation. The
condenser resolved it from the previous answer's text.

### The endpoint, and that the switch is really a switch

```
turn 2, switch OFF  standalone=None
                    hits=[Untrained Improvisation, Uncommon, Skill Actions, …]
turn 2, switch ON   standalone='What happens when a character untrained in Medicine
                                attempts Treat Wounds?'
                    hits=[Wounded, Godless Healing, Risky Surgery, …, Medicine, Treat Wounds]
prev_* sent with no switch: standalone=None   same hits as OFF? True
```

`Shift+Enter` follows up too:

```
look-up OFF  hits=[Untrained Improvisation, Uncommon, Skill Actions, Skill Training, Clever Improviser]
look-up ON   hits=[Medicine, Treat Wounds, Wounded, Godless Healing, Risky Surgery]
```

### Tests

`eval/test_followup.py`, 51 cases, same shape as `eval/test_score.py`. Eleven
of them are bad condenser replies; the rest defend the claim that the
single-turn path did not move — byte comparisons of the prompt and the system
string, and a stub client that counts calls so "no history, no extra call" is
asserted rather than asserted-in-a-comment.

```
51/51 cases pass          (eval/test_followup.py)
43/43 cases pass          (eval/test_score.py, unchanged)
```

---

## What is not measured, plainly

- **The hand-written gate was not run.** `eval/holdout.jsonl` is not in this
  checkout — `.gitignore` excludes `*.jsonl` and only `eval/benchmark.jsonl` and
  the seeds are committed. The argument that it cannot have moved is structural
  and is defended by tests, not by a run: with `history=None` the prompt, the
  system string and the sequence of model calls are identical, and the tests
  compare them byte for byte. That is a strong argument and it is still not a
  number. Anyone who has the file should run it before this ships.
- **No multi-turn benchmark exists.** Fourteen follow-ups written by one person
  is a smoke test. The honest version of this measurement needs the Tier 0
  treatment: mined from real conversations, judge-cross-checked, dev/test split.
  Real rules chats on Discord and Reddit are threaded, so the mining script has
  something to work with.
- **Answer quality on follow-ups is not measured at all**, only whether the
  right entry reaches the context. Reading the transcripts above, the 4B's
  follow-up answers wander in the same way its single-turn answers wander:
  thread 2 turn 2 pulls Grasping Earth and Improved Grab into an answer that did
  not need them. That is the model, not the feature, and no number here
  separates them.
- **Condensation inherits the previous turn's drift.** In a second run of thread
  1, turn three condensed to "How long must a character wait before attempting
  Treat Wounds again *after failing or being unable to perform it due to lacking
  proficiency*?", dragging turn two's untrained clause forward, and retrieval
  came back with Treat Disease and Treat Poison alongside Treat Wounds. The
  answer survived; the retrieval got noisier. This is the predictable cost of
  condensing against one turn instead of the whole thread, and it is also
  ordinary run-to-run non-determinism — the same chain condensed cleanly on the
  first run. Worth watching, not worth fixing blind.
- **Latency on the hardware this ships to is unmeasured.** Every number above is
  one desktop. The ratio held across five conditions; the seconds will not.
- **The page was not clicked in a browser.** Chrome in this environment could
  not reach the local server at all (an error interstitial on both `localhost`
  and `127.0.0.1`, while `curl` on the same URL returns 200), so the UI was
  verified three other ways: `node --check` over the page's script blocks, an
  audit that every id the script reaches for exists in the markup, and driving
  the exact HTTP requests the page makes — including that `prev_q` and `prev_a`
  sent *without* `followup=1` change nothing. That covers the wiring. It does
  not cover how the thread line looks or where it sits.

## What would change the design

1. **A multi-turn set of 100+ mined follow-ups.** Everything else here is
   guesswork about magnitudes. Gate for tuning any of it.
2. **Fold condense into rewrite after all**, if the extra call turns out to
   matter on a slow machine. It costs a prompt that no benchmark has been run
   with, so it needs that set first.
3. **Two turns instead of one**, same reason. The self-healing standalone chain
   is what makes one turn defensible, and the second run's drift is the evidence
   that it is not free.
4. **Skip the condense call when the follow-up is already standalone.** A
   question with a capitalised entity name and no pronoun almost never needs
   rewriting; a cheap classifier in front of the call would make most turns
   free. Unmeasured, and the current version is honest: it always asks, and the
   prompt tells the model to hand the question back unchanged, which it does.
