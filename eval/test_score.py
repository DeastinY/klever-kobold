#!/usr/bin/env python3
"""Regression tests for the contamination metric.

Four separate false-positive/negative bugs have been found in this metric by
reading model responses, and each fix widened or narrowed a matching window.
Widening risks laundering real leaks; narrowing risks punishing models that
explain themselves well. Every case below is taken verbatim from an actual run.

Run: python eval/test_score.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import score  # noqa: E402

# (text, forbidden term, should_count_as_a_leak)
CASES = [
    # --- real leaks, all observed ---------------------------------------------
    ("they become Unconscious and begin making Death Saving Throws.",
     "death saving throw", True),
    ("Short Rest: Typically 1 hour. You can take a short rest to recover some hit points.",
     "short rest", True),
    ("Focus points are typically recovered when you rest, such as during a short rest or long rest.",
     "short rest", True),
    ("they must attempt a Concentration check to maintain the spell.",
     "concentration check", True),
    ("You may spend a bonus action to attack.", "bonus action", True),
    ("You attack, but do not move; a bonus action lets you dash.", "bonus action", True),
    ("Since the player succeeded but did not critically succeed, they take half damage.",
     "half damage", True),

    # --- denials that must not count, all observed -----------------------------
    ("Pathfinder does not use hit dice.", "hit dice", False),
    ("There is no short rest mechanic.", "short rest", False),
    ("The Pathfinder 2e equivalent of inspiration is the Hero Point system.",
     "inspiration", False),
    ("Instead of using weight (pounds/kilograms), items are assigned a Bulk value.",
     "pounds", False),
    ("Unlike in D&D, there are no bonus actions.", "bonus action", False),
    ("There is no universal \u201cshort rest, spend Hit Dice\u201d mechanic like in D&D 5e.",
     "short rest", False),
    ("The Remaster removed alignment, so characters no longer have rules-defined labels "
     "like lawful good or chaotic neutral.", "lawful good", False),
    ("They are separate from spells cast using spell slots.", "spell slot", False),
    ("It does not have hit dice, short rests, or death saves.", "short rest", False),
]


# Exact/int cases: phrasing must not decide correctness.
EXACT_CASES = [
    ({"answer_type": "int", "question": "What level is the feat X?", "acceptable": ["14", "level 14"]},
     "Cleansing Transformation is 14th level. (Source: ...)", True),
    ({"answer_type": "int", "question": "What level is the feat X?", "acceptable": ["14", "level 14"]},
     "The feat is a level 14 feat.", True),
    ({"answer_type": "int", "question": "What level is the feat X?", "acceptable": ["1", "level 1"]},
     "It is 1st level.", True),
    ({"answer_type": "int", "question": "What level is the feat X?", "acceptable": ["14", "level 14"]},
     "It is 9th level.", False),
    ({"answer_type": "int", "question": "What level is the feat X?", "acceptable": ["14", "level 14"]},
     "It is level 140.", False),
]


# Set-grading cases. The gold sets and responses are verbatim from runs.
SET_CASES = [
    # prereq: gold is not drawn from the trait vocabulary, so the over-answering
    # check must not apply. "Dedication" is a trait name and also part of the
    # correct answer.
    ({"answer_type": "set", "question": "What are the prerequisites for the feat Dream Logic?",
      "acceptable": ["Sleepwalker Dedication"]},
     "Sleepwalker Dedication. [https://2e.aonprd.com/Feats.aspx?ID=8522]", True),
    # traits: gold IS the vocabulary, so a volunteered extra trait is a real error.
    ({"answer_type": "set", "question": "List every trait of the feat X.",
      "acceptable": ["Fighter", "Flourish"]},
     "It has the Fighter and Flourish traits.", True),
    ({"answer_type": "set", "question": "List every trait of the feat X.",
      "acceptable": ["Fighter", "Flourish"]},
     "It has the Fighter, Flourish and Magical traits.", False),
    ({"answer_type": "set", "question": "List every trait of the feat X.",
      "acceptable": ["Fighter", "Flourish"]},
     "It has the Fighter trait.", False),
]


# Refusal detection. Positives are verbatim from model runs; negatives are
# sentences that contain a negation but are answers, not refusals.
REFUSAL_CASES = [
    ('There is no creature called an "Anadi Seeker" in the provided excerpts.', True),
    ('I cannot confirm the existence of a feat called "Shoony Lore".', True),
    ("I don't see an item called \"Renewing Quills\" in the provided excerpts.", True),
    ('There is no spell called "Conductor\'s of Scattered Leaves" in Pathfinder 2e.', True),
    ('The feat "Gilded Rampart" does not appear in the provided rules excerpts.', True),
    ('The concept of "bardic inspiration dice" does not exist in Pathfinder 2e.', True),
    ("I can't find a feat named Scholar's Rain.", True),
    ("Metallic Envisionment isn't among the excerpts here.", True),
    ("No such feat exists in Pathfinder 2e.", True),
    ("The provided rules excerpts do not contain information about the Gilded Parry feat.", True),
    ("The excerpts don't mention that spell at all.", True),
    # typographic apostrophe, as models actually write it
    ("I can\u2019t find any Pathfinder 2e feat named \u201cAnimate Blade Stance\u201d.", True),
    ("I don\u2019t see that spell in the excerpts.", True),
    # answers that merely contain a negation
    ("There is no penalty on the first Strike; the second takes -5.", False),
    ("Cat Fall is a 1st-level feat that treats falls as shorter than they are.", False),
    ("No, a shield does not passively raise your AC; you must Raise a Shield.", False),
    ("The spell does not require a saving throw.", False),
    ("Fireball is a 3rd-rank spell dealing 6d6 fire damage.", False),
]


def main() -> int:
    failures = []
    for text, term, want_leak in CASES:
        hay = score.norm(text)
        mentioned = score.contains(hay, term)
        leak = mentioned and not score.denied(hay, term)
        if leak != want_leak:
            failures.append((text, term, want_leak, leak, mentioned))

    for text, term, want, got, mentioned in failures:
        print(f"FAIL {term!r} want_leak={want} got={got} (mentioned={mentioned})")
        print(f"     {text[:100]}")
    exact_failures = []
    for item, response, want in EXACT_CASES:
        item = {"id": "t", "family": "t", **item}
        got = score.grade(item, response, None)["correct"]
        if got != want:
            exact_failures.append((item["acceptable"], response, want, got))
    for gold, response, want, got in exact_failures:
        print(f"FAIL exact gold={gold} want={want} got={got}")
        print(f"     {response[:90]}")

    vocab = {"Fighter", "Flourish", "Magical", "Dedication", "Archetype"}
    set_failures = []
    for item, response, want in SET_CASES:
        item = {"id": "t", "family": "t", **item}
        got = score.grade(item, response, vocab)["correct"]
        if got != want:
            set_failures.append((item["acceptable"], response, want, got))
    for gold, response, want, got in set_failures:
        print(f"FAIL set gold={gold} want={want} got={got}")
        print(f"     {response[:90]}")

    refusal_failures = []
    for text, want in REFUSAL_CASES:
        got = score.refuses(text)
        if got != want:
            refusal_failures.append((text, want, got))
    for text, want, got in refusal_failures:
        print(f"FAIL refusal want={want} got={got}\n     {text[:88]}")

    total = len(CASES) + len(SET_CASES) + len(EXACT_CASES) + len(REFUSAL_CASES)
    passed = (total - len(failures) - len(set_failures) - len(exact_failures)
              - len(refusal_failures))
    print(f"\n{passed}/{total} cases pass")
    return 1 if failures or set_failures or exact_failures or refusal_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
