#!/usr/bin/env python3
"""Does condensing a follow-up put the right entry back in the context window?

A follow-up is elliptical -- "what if she's untrained?" is three stopwords and a
pronoun -- and retrieval here is entirely query-driven. This probe measures the
one thing that matters before anything else can work: with the switch off and
with it on, is the entry the follow-up is *about* among the eight excerpts?

Each thread below is an opening question and one or two follow-ups, and each
follow-up names the entries that would have to be retrieved for any answer to
be possible. No grading of prose, no judge, no model of a model: a name is in
the top eight or it is not.

**This is a smoke test, not a benchmark.** It is a couple of dozen follow-ups
written by the same person who wrote the feature, which is the exact failure
mode Tier 0 of the roadmap exists to fix. It can show that a change is not
working. It cannot show by how much one works, and no number from it belongs in
a README.

Run:  python eval/followup_probe.py --index dist/kobold-index [--llm-model qwen3.5:4b]
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kleverkobold.app import DEFAULT_INDEX, DEFAULT_OLLAMA, Assistant, Turn  # noqa: E402

# (opening question, [(follow-up, {names, any of which answers it})])
#
# The gold names are entry names as the Archives of Nethys spells them; the
# probe says so loudly when one is not in the index, because a label that
# matches nothing scores zero for both arms and looks like a tie.
THREADS = [
    ("How does Treat Wounds work?", [
        ("what if she's untrained?", {"Treat Wounds", "Medicine"}),
        ("how long do we have to wait before trying again?", {"Treat Wounds"}),
    ]),
    ("What does the grabbed condition do?", [
        ("can I still cast spells?", {"Grabbed"}),
        ("what about a spell with a somatic component?", {"Somatic", "Grabbed"}),
    ]),
    ("Tell me about the Escape action.", [
        ("what skills can I use for it?", {"Escape"}),
    ]),
    ("How does Battle Medicine work?", [
        ("what level is it?", {"Battle Medicine"}),
        ("how does that differ from the one that takes ten minutes?",
         {"Treat Wounds", "Battle Medicine"}),
    ]),
    ("Is there a feat that makes falling less dangerous?", [
        ("what level is it?", {"Cat Fall", "Plummeting Roll"}),
    ]),
    ("What does the frightened condition do?", [
        ("how does it go away?", {"Frightened"}),
    ]),
    ("How does Demoralize work?", [
        ("which skill is it?", {"Demoralize"}),
        ("and can I use it on the same creature twice?", {"Demoralize"}),
    ]),
    ("How does Raise a Shield work?", [
        ("what happens when I block with it?", {"Shield Block", "Raise a Shield"}),
    ]),
    ("What does the Grapple action do?", [
        ("what if I critically fail?", {"Grapple"}),
    ]),
    ("How does the Sneak action work?", [
        ("can I do it while someone is watching me?", {"Sneak"}),
    ]),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=pathlib.Path, default=DEFAULT_INDEX)
    ap.add_argument("--ollama", default=DEFAULT_OLLAMA)
    ap.add_argument("--llm-model", default=None)
    ap.add_argument("-k", type=int, default=8)
    ap.add_argument("--rerank", action="store_true",
                    help="the Better preset's setting; the shipped 4B runs without it")
    args = ap.parse_args()

    a = Assistant(args.index, args.ollama, llm_model=args.llm_model)
    known = {(m.get("name") or "") for m in a.index.meta}
    unknown = sorted({g for _, ups in THREADS for _, gold in ups for g in gold
                      if g not in known})
    if unknown:
        print(f"!! gold names not in the index, so both arms score 0 on them: {unknown}\n")

    off_hits = on_hits = total = 0
    condense_s: list[float] = []
    for opening, follow_ups in THREADS:
        print(f"\n{opening}")
        plan, hits, _ = a.retrieve(opening, k=args.k, rerank=args.rerank)
        turn = Turn(question=opening, answer="", standalone="")
        # The probe answers nothing, so there is no previous answer to carry --
        # which makes this the *harder* arm for the feature: the condenser has
        # the previous question and nothing else. In the app it also sees the
        # answer, where the entity names are thickest.
        for follow_up, gold in follow_ups:
            total += 1
            _, cold, _ = a.retrieve(follow_up, k=args.k, rerank=args.rerank)
            t = time.time()
            plan, warm, _ = a.retrieve(follow_up, k=args.k, rerank=args.rerank,
                                       history=[turn])
            condense_s.append(time.time() - t)
            cold_names = [h.name for h in cold]
            warm_names = [h.name for h in warm]
            off = bool(gold & set(cold_names))
            on = bool(gold & set(warm_names))
            off_hits += off
            on_hits += on
            mark = {(False, True): "  FIXED", (True, False): "  BROKE",
                    (True, True): "  both ", (False, False): "  neither"}[(off, on)]
            print(f"{mark}  {follow_up}")
            print(f"           read as: {plan.get('standalone', '')!r}")
            print(f"           want any of {sorted(gold)}")
            print(f"           off: {cold_names}")
            print(f"           on : {warm_names}")
            turn = Turn(question=follow_up, answer="",
                        standalone=plan.get("standalone", ""))

    print(f"\n{total} follow-ups across {len(THREADS)} threads, k={args.k}, "
          f"rerank={'on' if args.rerank else 'off'}, no previous answer carried")
    print(f"  switch off:  {off_hits}/{total}")
    print(f"  switch on:   {on_hits}/{total}")
    print(f"  the condensed follow-up cost {sum(condense_s) / len(condense_s):.2f}s per "
          f"question on this machine, retrieval included")
    print("\nToo few items to be a benchmark. Read the lines above, not the fractions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
