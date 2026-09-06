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
    r"instead of", r"equivalent of", r"equivalent to", r"analogue of", r"no such",
    r"replaces?", r"replaced", r"removed", r"lacks", r"lack", r"unlike in",
    r"as in", r"in 5e", r"in d&d", r"dungeons & dragons", r"fifth edition",
    r"5th edition", r"other rpgs?", r"other systems?", r"does away with",
)
RE_NEGATION = "|".join(NEGATION_CUES)


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
    """True when ``term`` is governed by a negation or contrast cue, not asserted."""
    # Separators are limited to spaces, commas and hyphens so the cue cannot reach
    # across a clause break: "do not move; a bonus action lets you dash" is a leak.
    gap = r"(?:[ ,\-]+[\w'’]+){0,4}[ ,\-]+"
    pattern = rf"(?:{RE_NEGATION}){gap}{re.escape(norm(term).strip())}(?:e?s)?(?![\w-])"
    return re.search(pattern, haystack) is not None


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
        if vocab:
            goldset = {norm(g) for g in gold}
            extra = sorted(v for v in vocab if norm(v) not in goldset and contains(hay, v))
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
        if fam == "trap_5e":
            entry["contaminated"] = sum(1 for v in rows if v["forbidden_hits"])
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

    missing = set(items) - set(responses)
    if missing:
        print(f"warning: {len(missing)} items have no response", file=sys.stderr)

    vocab = load_vocab(args.chunks)
    verdicts = [grade(items[i], responses[i], vocab) for i in items if i in responses]
    report = summarise(verdicts)
    report["run"] = args.responses.stem
    if vocab:
        report["trait_vocab"] = len(vocab)

    label = args.responses.stem
    print(f"\n{label}   {report['correct']}/{report['items']}  ({report['accuracy']:.1%})\n")
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
