#!/usr/bin/env python3
"""Regression tests for follow-up questions.

Two things are being defended here, and only the second one is about
follow-ups at all:

1. **With no history, nothing changed.** The 89.9% on the hand-written gate was
   measured with one particular system string and one particular prompt layout.
   Every single-turn assertion below is a byte comparison against the
   expression this file replaced, because a prompt that drifts by a newline is
   a benchmark number that no longer describes the program.
2. **A condensation that goes wrong degrades to today's behaviour.** The model
   is asked for one line and given no way to be checked, so every reply it can
   plausibly produce -- a label, a preamble, quotes, silence, an essay -- is
   a case here, and each one either yields a usable question or hands back the
   one that was typed.

No model and no index: the client is a stub and the entries are made up.

Run: python eval/test_followup.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from kleverkobold import server
from kleverkobold.app import (
    ANSWER_SYSTEM,
    HISTORY_CHARS,
    Assistant,
    Hit,
    OllamaError,
    Turn,
)

FOLLOW_UP = "what if she's untrained?"
EARLIER = Turn(question="How does Treat Wounds work?",
               answer="Treat Wounds is a 10-minute Medicine activity.")

# (what the model replied, what condense should hand back)
# Every row except the last two is a shape a 4B has actually produced or is one
# formatting slip away from producing.
CONDENSE_CASES = [
    # The reply asked for: one bare line.
    ("What happens when a character untrained in Medicine attempts Treat Wounds?",
     "What happens when a character untrained in Medicine attempts Treat Wounds?"),
    # The label it was shown in the examples and usually omits.
    ("Rewritten: Can a grabbed creature still cast spells?",
     "Can a grabbed creature still cast spells?"),
    ("rewritten:  Can a grabbed creature still cast spells?",
     "Can a grabbed creature still cast spells?"),
    # A preamble in front of the labelled line: the label wins, not the order.
    ("Sure, here is the rewritten question.\nRewritten: What level is Cat Fall?",
     "What level is Cat Fall?"),
    # Quoted, which small models do when a prompt says "reply with the question".
    ('"What level is Cat Fall?"', "What level is Cat Fall?"),
    ("'What level is Cat Fall?'", "What level is Cat Fall?"),
    # Numbered, the way a list-shaped reply comes out.
    ("1. What level is Cat Fall?", "What level is Cat Fall?"),
    # Nothing usable: keep what was typed rather than searching for "".
    ("", FOLLOW_UP),
    ("   \n  \n", FOLLOW_UP),
    ("Rewritten:", FOLLOW_UP),
    # It answered instead of rewriting. 300 characters is the line: past it the
    # reply is prose, and prose retrieves worse than the original three words.
    ("Rewritten: " + "The character cannot attempt it because " * 12, FOLLOW_UP),
]

# (query string as the page would send it, expected number of turns)
HISTORY_CASES = [
    ({}, 0),
    ({"prev_q": ["How does Treat Wounds work?"], "prev_a": ["10 minutes."]}, 0),
    ({"followup": ["1"]}, 0),
    ({"followup": ["1"], "prev_q": ["   "]}, 0),
    ({"followup": ["0"], "prev_q": ["How does Treat Wounds work?"]}, 0),
    ({"followup": ["1"], "prev_q": ["How does Treat Wounds work?"]}, 1),
    ({"followup": ["1"], "prev_q": ["How does Treat Wounds work?"],
      "prev_a": ["10 minutes."], "prev_std": ["How does Treat Wounds work?"]}, 1),
]


class Stub:
    """Stands in for Ollama. Counts calls, so "no history, no extra call" is
    something a test can actually assert rather than something a comment claims."""

    def __init__(self, reply="", fail=False):
        self.reply, self.fail, self.calls, self.prompts = reply, fail, 0, []

    def chat(self, system, user, model, max_tokens=700, keep_alive=""):
        self.calls += 1
        self.prompts.append((system, user))
        if self.fail:
            raise RuntimeError("the backend fell over mid-condense")
        return self.reply


def assistant(stub):
    """An Assistant with no index behind it. `condense` and `prompt` touch the
    client, the manifest and one integer, and nothing else."""
    a = Assistant.__new__(Assistant)
    a.ollama = stub
    a.manifest = {"ollama_llm": "qwen3.5:4b"}
    a.context_chars = 1600
    return a


HITS = [Hit(chunk_id="a", name="Treat Wounds", category="action", level=None,
            url="https://2e.aonprd.com/Actions.aspx?ID=2399", text="Ten minutes.",
            summary="Restore Hit Points over ten minutes."),
        Hit(chunk_id="b", name="Medicine", category="skill", level=None,
            url="https://2e.aonprd.com/Skills.aspx?ID=42", text="A skill.",
            summary="Patch wounds.")]


def main() -> int:
    failures = []

    def check(name, got, want):
        if got != want:
            failures.append((name, want, got))

    # --- condensation, and every way it can go wrong -------------------------
    for raw, want in CONDENSE_CASES:
        a = assistant(Stub(raw))
        check(f"condense {raw[:44]!r}", a.condense(FOLLOW_UP, [EARLIER]), want)

    # A backend that breaks mid-call leaves the question exactly as typed.
    a = assistant(Stub(fail=True))
    check("condense survives a broken backend", a.condense(FOLLOW_UP, [EARLIER]), FOLLOW_UP)

    # ...but a backend that is *missing* is the user's problem to see, not
    # something to swallow into a silently worse search.
    class Down(Stub):
        def chat(self, *args, **kwargs):
            raise OllamaError("Cannot reach Ollama.")

    try:
        assistant(Down()).condense(FOLLOW_UP, [EARLIER])
        failures.append(("condense re-raises OllamaError", "raised", "returned"))
    except OllamaError:
        pass

    # No history is not a conversation, and must not cost a model call.
    stub = Stub("something")
    check("condense with no history", assistant(stub).condense(FOLLOW_UP, []), FOLLOW_UP)
    check("condense with no history makes no call", stub.calls, 0)

    # Only the last turn is shown, and it is shown by its condensed form.
    stub = Stub("x")
    older = Turn(question="How does Battle Medicine work?", answer="One action.")
    newer = Turn(question="and the ten minute one?", answer="Treat Wounds.",
                 standalone="How does Treat Wounds work?")
    assistant(stub).condense(FOLLOW_UP, [older, newer])
    sent = stub.prompts[0][1]
    check("condense shows the last turn", "How does Treat Wounds work?" in sent, True)
    check("condense shows its standalone, not its raw text",
          "and the ten minute one?" in sent, False)
    check("condense does not show the turn before last",
          "Battle Medicine" in sent, False)
    check("Turn.asked prefers the standalone", newer.asked(), "How does Treat Wounds work?")
    check("Turn.asked falls back to the question", older.asked(),
          "How does Battle Medicine work?")

    # --- the single-turn prompt has not moved --------------------------------
    a = assistant(Stub())
    q = "How does Treat Wounds work?"
    check("single-turn prompt is unchanged",
          a.prompt(q, HITS), a.context(HITS) + "\n\nQuestion: " + q)
    check("single-turn system string is unchanged", a.answer_system(), ANSWER_SYSTEM)
    check("single-turn system string is unchanged (empty history)",
          a.answer_system([]), ANSWER_SYSTEM)
    check("single-turn prompt has no conversation block",
          "<earlier_exchange>" in a.prompt(q, HITS), False)
    check("empty history is not a conversation", a.prompt(q, HITS, []), a.prompt(q, HITS))

    # --- the follow-up prompt ------------------------------------------------
    built = a.prompt(FOLLOW_UP, HITS, [EARLIER])
    check("follow-up prompt opens with the earlier turn",
          built.startswith("<earlier_exchange>\nQuestion: How does Treat Wounds work?"), True)
    check("follow-up prompt ends with the question asked",
          built.endswith("\n\nQuestion: " + FOLLOW_UP), True)
    # The excerpts must still be the last thing before the question: `named_last`
    # puts the entry the question names at the end of them on purpose.
    check("the earlier turn sits before the excerpts, not between them and the question",
          built.index("</earlier_exchange>") < built.index("<rules_excerpts>"), True)
    check("follow-up system string says the earlier answer is not a source",
          a.answer_system([EARLIER]).startswith(ANSWER_SYSTEM), True)
    check("follow-up system string differs from the single-turn one",
          a.answer_system([EARLIER]) != ANSWER_SYSTEM, True)

    long_turn = Turn(question="q" * 900, answer="a" * 4000)
    block = a.earlier([long_turn])
    check("a runaway earlier answer is capped", "a" * (HISTORY_CHARS + 1) in block, False)
    check("the earlier answer is carried up to the cap", "a" * HISTORY_CHARS in block, True)
    check("a runaway earlier question is capped", "q" * 401 in block, False)
    check("no earlier turn, no block", a.earlier(None), "")
    check("no earlier turn, no block (empty)", a.earlier([]), "")

    # --- retrieve wires the condensed question through, and only then --------
    def wired(history):
        stub = Stub("What happens when a character untrained in Medicine attempts Treat Wounds?")
        a = assistant(stub)
        seen = {}
        a.rewrite = lambda question: (seen.setdefault("rewrite", question) and {}) or {}
        a.search = lambda question, **kw: (seen.setdefault("search", question) and []) or []
        a.rerank = lambda question, hits, k: (seen.setdefault("rerank", question) and []) or []
        plan, _hits, timings = a.retrieve("what if she's untrained?", history=history)
        return plan, timings, seen, stub

    plan, timings, seen, stub = wired(None)
    check("no history, no condense call", stub.calls, 0)
    check("no history, no condense timing", "condense" in timings, False)
    check("no history, no standalone on the plan", "standalone" in plan, False)
    check("no history, retrieval sees the question as typed",
          seen["search"], "what if she's untrained?")

    plan, timings, seen, stub = wired([EARLIER])
    condensed = "What happens when a character untrained in Medicine attempts Treat Wounds?"
    check("history, exactly one condense call", stub.calls, 1)
    check("history, condense is timed", "condense" in timings, True)
    check("history, the plan carries the standalone", plan.get("standalone"), condensed)
    for stage in ("rewrite", "search", "rerank"):
        check(f"history, {stage} sees the condensed question", seen[stage], condensed)

    # `named_last` matches names in the question, so it only starts working on
    # a follow-up once condensation has put a name back into it. This is the
    # quiet second win of the feature and it is free.
    check("named_last does nothing for an elliptical follow-up",
          Assistant.named_last("what if she's untrained?", HITS), HITS)
    check("named_last works on the condensed question",
          Assistant.named_last("How soon can Treat Wounds be tried again?", HITS),
          [HITS[1], HITS[0]])

    # --- the endpoint parameter ----------------------------------------------
    for query, want in HISTORY_CASES:
        check(f"_read_history {query}", len(server._read_history(query)), want)

    capped = server._read_history({"followup": ["1"], "prev_q": ["q" * 900],
                                   "prev_a": ["a" * 4000], "prev_std": ["s" * 900]})[0]
    check("endpoint caps the previous question", len(capped.question), 400)
    check("endpoint caps the previous answer", len(capped.answer), HISTORY_CHARS)
    check("endpoint caps the previous standalone", len(capped.standalone), 400)

    for name, want, got in failures:
        print(f"FAIL {name}\n     want={want!r}\n     got ={got!r}")
    total = (len(CONDENSE_CASES) + len(HISTORY_CASES) + 33)
    print(f"\n{total - len(failures)}/{total} cases pass")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
