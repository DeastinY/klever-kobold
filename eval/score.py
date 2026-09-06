#!/usr/bin/env python3
"""Score model responses against the PF2e benchmark.

Every family is graded deterministically.  No LLM judge is involved in any
headline number: the point of the benchmark is that ``trap_5e`` contamination
and exact-attribute recall are both detectable by string matching, so scores are
cheap, reproducible, and not themselves dependent on a model's opinion.

Grading by ``answer_type``:

``int`` / ``exact``
    Any string in ``acceptable`` appearing on a word boundary counts as correct.
``set``
    Recall over ``acceptable``.  Where a vocabulary is supplied (the corpus trait
    list), also measures *over-answering*: vocabulary terms asserted but not in
    the gold set.  A model that lists every trait it can think of should not
    score well on "list every trait of X".
``abstain``
    Correct only if the response declines.  Separately counts the failure mode we
    actually care about -- confidently asserting a level for a feat that does not
    exist.
``free`` (``trap_5e``)
    ``must_not_contain`` is the metric.  A response containing "bonus action" or
    "death saving throw" is answering in the wrong game system regardless of how
    fluent it is.

``must_not_contain`` is also applied to ``remaster_rename``, where the forbidden
string is the legacy name the model is expected to reach for.

Two corrections keep the contamination metric honest, both found by reading the
first run's responses rather than its scores:

1. **A term that appears in the question cannot count against the answer.**
   "Does the game have an Insight skill?" cannot be answered without saying
   "Insight skill".  Naive substring matching scored four correct refutations as
   contamination.
2. **An explicit denial is not a use.**  "Pathfinder does not use hit dice" is
   the right answer, not a 5e leak, so a forbidden term directly governed by a
   negation or contrast cue is excused.  The window is deliberately tight -- a
   loose one would excuse real contamination sitting in the same sentence as an
   unrelated "not".

Both the raw and the adjusted counts are kept per item so the metric can be
audited rather than trusted.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import re
import sys

import orjson

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Phrases that mean "I am not answering this", for the abstention family.
REFUSALS = (
    "does not exist", "doesn't exist", "no such", "not a pathfinder", "not a real",
    "cannot find", "can't find", "unable to find", "not aware of", "no record",
    "i don't know", "i do not know", "not familiar", "no feat named", "no feat called",
    "not an official", "isn't an official", "couldn't find", "could not find",
    "unaware of", "not something i", "made up", "fictional", "not in pathfinder",
)
RE_LEVEL_CLAIM = re.compile(r"\blevel\s+(\d{1,2})\b|\bis\s+a\s+(\d{1,2})(?:st|nd|rd|th)[- ]level\b", re.I)

# Cues that turn a mention into a denial. Matched only when they directly govern
# the term -- at most four words in between -- so an unrelated "not" elsewhere in
# the sentence does not launder a real leak.
NEGATION_CUES = (
    r"no", r"not", r"n't", r"never", r"without", r"unlike", r"rather than",
    r"instead of", r"instead", r"equivalent of", r"equivalent to", r"analogue of",
    r"no such", r"no longer", r"replaces?", r"replaced", r"removed", r"lacks",
    r"lack", r"unlike in", r"as in", r"in 5e", r"in d&d", r"dungeons & dragons",
    r"fifth edition", r"5th edition", r"other rpgs?", r"other systems?",
    r"does away with", r"separate from", r"distinct from", r"as opposed to",
    r"differs? from", r"there is no", r"nothing like", r"not like",
)
RE_NEGATION = "|".join(NEGATION_CUES)
RE_CLAUSE_BREAK = re.compile(r"[.;:!?]")
# A comma followed by a fresh subject starts a new clause, so the cue before it
# does not govern what comes after.
RE_NEW_SUBJECT = re.compile(r",\s*(?:they|you|it|we|i|he|she|there|this|that)\b")


def norm(text: str) -> str:
    text = text.lower().replace("’", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text)


def contains(haystack: str, needle: str) -> bool:
    """Word-boundary containment, tolerating a plural.

    'rare' must not match inside 'rarely', but "there are no bonus actions" has
    to count as a mention of "bonus action" -- models pluralise freely and an
    exact-boundary match silently misses half the contamination.
    """
    needle = norm(needle).strip()
    if not needle:
        return False
    return re.search(rf"(?<![\w-]){re.escape(needle)}(?:e?s)?(?![\w-])", haystack) is not None


def denied(haystack: str, term: str) -> bool:
    """True when ``term`` is governed by a negation or contrast cue, not asserted.

    Scanning the gap text explicitly rather than with one large regex, because the
    rule has three separate parts and each was added to fix an observed
    misclassification:

    * **at most eight words.** A four-word window punished models that explain the
      contrast -- "characters no longer have rules-defined labels like lawful
      good" is a correct refutation.
    * **no clause terminator.** "do not move; a bonus action lets you dash" is a
      leak; the cue belongs to a different clause.
    * **no comma followed by a new subject.** "did not critically succeed, they
      take half damage" is a leak for the same reason, but a comma alone cannot
      be the test -- "does not have hit dice, short rests, or death saves" is a
      denial whose terms sit in a list under the same verb.
    """
    needle = norm(term).strip()
    if not needle:
        return False
    pattern = re.compile(rf"(?<![\w-]){re.escape(needle)}(?:e?s)?(?![\w-])")
    cue = re.compile(rf"(?:(?<![\w-])|^)(?:{RE_NEGATION})(?![\w-])")

    for hit in pattern.finditer(haystack):
        window = haystack[max(0, hit.start() - 140):hit.start()]
        cues = list(cue.finditer(window))
        if not cues:
            continue
        gap = window[cues[-1].end():]
        if RE_CLAUSE_BREAK.search(gap):
            continue
        if RE_NEW_SUBJECT.search(gap):
            continue
        if len(gap.split()) > 8:
            continue
        return True
    return False


def scorable_forbidden(item: dict) -> list[str]:
    """Forbidden terms the answer could actually have avoided.

    A term already present in the question is unavoidable in any coherent answer,
    so it is dropped before scoring.
    """
    question = norm(item.get("question", ""))
    return [f for f in (item.get("must_not_contain") or []) if not contains(question, f)]


def grade(item: dict, response: str, vocab: set[str] | None = None) -> dict:
    """Return a per-item verdict: ``correct`` plus family-specific diagnostics."""
    hay = norm(response or "")
    out: dict = {"id": item["id"], "family": item["family"]}

    # An empty response must never score. It is silently "clean" under a negative
    # check like trap_5e, which would let a truncated run look like a perfect one.
    out["empty"] = not (response or "").strip()
    if out["empty"]:
        out["forbidden_hits"] = []
        out["forbidden_mentioned"] = []
        out["forbidden_echoed_from_question"] = []
        out["correct"] = False
        if item["answer_type"] == "set":
            out["recall"] = 0.0
            out["missing"] = list(item["acceptable"])
        if item["answer_type"] == "abstain":
            out["fabricated"] = False
        if item["answer_type"] == "free":
            out["clean"] = False
        return out

    candidates = scorable_forbidden(item)
    mentioned = [f for f in candidates if contains(hay, f)]
    forbidden = [f for f in mentioned if not denied(hay, f)]
    out["forbidden_hits"] = forbidden
    out["forbidden_mentioned"] = mentioned
    out["forbidden_echoed_from_question"] = [
        f for f in (item.get("must_not_contain") or []) if f not in candidates
    ]

    kind = item["answer_type"]
    if kind in ("int", "exact"):
        out["correct"] = any(contains(hay, a) for a in item["acceptable"]) and not forbidden

    elif kind == "set":
        gold = item["acceptable"]
        found = [g for g in gold if contains(hay, g)]
        out["recall"] = len(found) / len(gold) if gold else 0.0
        out["missing"] = [g for g in gold if g not in found]

        # Over-answering is only measurable where the gold set is drawn from a
        # closed vocabulary -- i.e. trait questions. Applying it to prerequisites
        # was a category error: "Dedication" is itself a trait name, so
        # "Sleepwalker Dedication" -- the exactly correct answer -- was scored as
        # naming a trait that was not asked for.
        gold_norm = [norm(g) for g in gold]
        vocab_drawn = bool(vocab) and all(any(g == norm(v) for v in vocab) for g in gold_norm)
        if vocab_drawn:
            question = norm(item.get("question", ""))
            extra = sorted(
                v for v in vocab
                if norm(v) not in gold_norm
                # a term inside a gold answer, or already in the question, is not
                # something the model volunteered
                and not any(norm(v) in g for g in gold_norm)
                and not contains(question, v)
                and contains(hay, v)
            )
            out["extra"] = extra
            out["correct"] = out["recall"] == 1.0 and not extra
        else:
            out["correct"] = out["recall"] == 1.0

    elif kind == "abstain":
        refused = any(r in hay for r in REFUSALS)
        out["correct"] = refused
        # The interesting failure is not "did not refuse" but "invented a level".
        out["fabricated"] = bool(RE_LEVEL_CLAIM.search(response or "")) and not refused

    elif kind == "free":
        out["correct"] = not forbidden
        out["clean"] = not forbidden
        # Staying clean is a negative check, and silence passes it. Where the item
        # names the Pathfinder machinery the ruling needs, measure that too.
        wanted = item.get("must_contain") or []
        if wanted:
            present = [w for w in wanted if contains(hay, w)]
            out["grounding"] = len(present) / len(wanted)
            out["missing"] = [w for w in wanted if w not in present]

    else:  # pragma: no cover
        raise ValueError(f"unknown answer_type {kind!r}")

    return out


def load_vocab(chunks: pathlib.Path) -> set[str]:
    """Trait names from the corpus, used to detect over-answering on trait questions."""
    if not chunks.exists():
        return set()
    vocab = set()
    for line in chunks.open("rb"):
        row = orjson.loads(line)
        if row.get("category") == "trait" and row.get("name"):
            vocab.add(row["name"])
    return vocab


def summarise(verdicts: list[dict]) -> dict:
    by_family: dict[str, dict] = {}
    for fam in sorted({v["family"] for v in verdicts}):
        rows = [v for v in verdicts if v["family"] == fam]
        n = len(rows)
        entry = {"n": n, "correct": sum(v["correct"] for v in rows)}
        entry["accuracy"] = entry["correct"] / n if n else 0.0
        if any("recall" in v for v in rows):
            entry["mean_recall"] = sum(v.get("recall", 0.0) for v in rows) / n
            entry["over_answered"] = sum(1 for v in rows if v.get("extra"))
        if any("fabricated" in v for v in rows):
            entry["fabricated"] = sum(1 for v in rows if v.get("fabricated"))
        empty = sum(1 for v in rows if v.get("empty"))
        if empty:
            entry["empty"] = empty
        if fam.startswith("trap_5e"):
            entry["contaminated"] = sum(1 for v in rows if v["forbidden_hits"])
        if any("grounding" in v for v in rows):
            entry["mean_grounding"] = sum(v.get("grounding", 0.0) for v in rows) / n
        if fam == "remaster_rename":
            entry["used_legacy_name"] = sum(1 for v in rows if v["forbidden_hits"])
        by_family[fam] = entry

    total = len(verdicts)
    return {
        "items": total,
        "correct": sum(v["correct"] for v in verdicts),
        "accuracy": sum(v["correct"] for v in verdicts) / total if total else 0.0,
        "families": by_family,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("responses", type=pathlib.Path, help="jsonl of {id, response}")
    ap.add_argument("--benchmark", type=pathlib.Path, default=ROOT / "eval" / "benchmark.jsonl")
    ap.add_argument("--chunks", type=pathlib.Path, default=ROOT / "data" / "processed" / "aon_chunks.jsonl")
    ap.add_argument("--out", type=pathlib.Path, help="write the full report as json")
    args = ap.parse_args()

    items = {orjson.loads(l)["id"]: orjson.loads(l) for l in args.benchmark.open("rb")}
    responses = {}
    for line in args.responses.open("rb"):
        row = orjson.loads(line)
        responses[row["id"]] = row.get("response", "")

    # Items whose premise turned out to be false are not scored against anyone.
    excluded = [i for i in items if items[i].get("excluded")]

    missing = set(items) - set(responses) - set(excluded)
    if missing:
        print(f"warning: {len(missing)} items have no response", file=sys.stderr)

    vocab = load_vocab(args.chunks)
    verdicts = [grade(items[i], responses[i], vocab)
                for i in items if i in responses and not items[i].get("excluded")]
    report = summarise(verdicts)
    report["run"] = args.responses.stem
    report["benchmark_items"] = len(items) - len(excluded)
    report["excluded_items"] = len(excluded)
    # A control run deliberately covers only some families; the dossier lists
    # those separately rather than showing a misleading overall figure.
    report["partial"] = len(verdicts) < len(items) - len(excluded)
    if vocab:
        report["trait_vocab"] = len(vocab)

    label = args.responses.stem
    print(f"\n{label}   {report['correct']}/{report['items']}  ({report['accuracy']:.1%})")
    if excluded:
        print(f"  ({len(excluded)} items excluded: premise false)")
    print()
    print(f"  {'family':18s} {'n':>4s} {'correct':>8s} {'acc':>7s}   notes")
    print(f"  {'-' * 18} {'-' * 4} {'-' * 8} {'-' * 7}   {'-' * 30}")
    for fam, e in report["families"].items():
        notes = []
        if "mean_recall" in e:
            notes.append(f"recall {e['mean_recall']:.0%}")
        if e.get("over_answered"):
            notes.append(f"over-answered {e['over_answered']}")
        if "fabricated" in e:
            notes.append(f"fabricated a level {e['fabricated']}x")
        if "contaminated" in e:
            notes.append(f"5e vocabulary in {e['contaminated']}/{e['n']}")
        if "mean_grounding" in e:
            notes.append(f"pf2e machinery {e['mean_grounding']:.0%}")
        if e.get("empty"):
            notes.append(f"{e['empty']} empty")
        if "used_legacy_name" in e:
            notes.append(f"answered with legacy name {e['used_legacy_name']}x")
        print(f"  {fam:18s} {e['n']:4d} {e['correct']:8d} {e['accuracy']:6.1%}   {', '.join(notes)}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(orjson.dumps({"report": report, "verdicts": verdicts},
                                          option=orjson.OPT_INDENT_2))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
