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
    print(f"\n{len(CASES) - len(failures)}/{len(CASES)} cases pass")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
