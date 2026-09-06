#!/usr/bin/env python3
"""Generate the PF2e rules benchmark from the normalised AoN corpus.

No public benchmark for Pathfinder 2e rules QA exists, so we build one that is
*machine-checkable*: every generated item's answer is derived from a structured
AoN field, not from a model's opinion.  Six families, each probing a different
failure mode:

``lookup_level`` / ``lookup_traits`` / ``lookup_rarity``
    Flat recall of exact attributes.  This is what retrieval should nail and
    what a fine-tune alone will hallucinate.
``prereq``
    Multi-hop: a feat's prerequisites, which require following the entity graph.
``remaster_rename``
    The Remaster renamed ~2k entities.  Models trained on pre-2023 web text
    answer with legacy names; this measures that specific staleness.

    Two corrections, found by diagnosing why retrieval capped at 65% here while
    every other family sat at 97-100%.  AoN's ``legacy_name`` is many-to-one:
    "Tanglefoot Bag" is claimed by Glue Bomb and all four of its grades, so
    demanding one particular grade punishes a correct answer.  Every claimant is
    now acceptable.  And where the legacy name is *still* a live entry --
    Invisibility, Perfected Form -- the question's premise is simply false, so
    those items are marked excluded rather than scored.
``abstention``
    Plausible-sounding entities that do not exist.  Measures whether the model
    will invent a feat rather than say it cannot find one.
``trap_5e``
    Hand-authored (``seeds/5e_traps.jsonl``).  Questions where the D&D 5e answer
    is confidently wrong for PF2e.  ``must_not_contain`` turns each into an
    automatic scorer for 5e contamination.
``trap_5e_applied``
    Hand-authored (``seeds/5e_traps_applied.jsonl``).  The v1 traps ask leading
    questions -- "does Pathfinder use advantage?" telegraphs that the answer is
    no, and both frontier models scored 30/30.  These instead ask the model to
    *adjudicate a situation*, and check whether 5e machinery shows up in the
    ruling.  ``must_contain`` additionally measures whether the right Pathfinder
    machinery appears, reported separately from contamination.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import random
import re
import sys

import orjson

ROOT = pathlib.Path(__file__).resolve().parents[1]
RE_PREREQ = re.compile(r"\*\*Prerequisites?\*\*\s*(.+)")

# Categories whose names read naturally in a question.
QUESTIONABLE = {
    "feat", "spell", "action", "creature", "equipment", "weapon", "armor",
    "shield", "hazard", "ritual", "background", "archetype", "heritage",
    "class-feature", "condition", "trait", "deity", "relic",
}


def load(path: pathlib.Path) -> list[dict]:
    return [orjson.loads(line) for line in path.open("rb")]


def unique_named(rows: list[dict]) -> dict[str, dict]:
    """Entities whose name is unambiguous corpus-wide -- safe to ask about by name."""
    counts = collections.Counter(r["name"] for r in rows if r["name"])
    return {r["name"]: r for r in rows if r["name"] and counts[r["name"]] == 1}


def _item(family: str, n: int, **kw) -> dict:
    return {"id": f"{family}-{n:04d}", "family": family, **kw}


def gen_lookup_level(pool: list[dict], rng: random.Random, n: int) -> list[dict]:
    cands = [r for r in pool if r["level"] is not None and r["category"] in QUESTIONABLE]
    out = []
    for i, r in enumerate(rng.sample(cands, min(n, len(cands)))):
        noun = "creature" if r["category"] == "creature" else r["category"].replace("-", " ")
        out.append(_item(
            "lookup_level", i,
            question=f"In Pathfinder 2e, what level is the {noun} {r['name']}?",
            answer=str(r["level"]), answer_type="int",
            acceptable=[str(r["level"]), f"level {r['level']}"],
            source_ids=[r["id"]], source_urls=[r["url"]],
        ))
    return out


def gen_lookup_traits(pool: list[dict], rng: random.Random, n: int) -> list[dict]:
    cands = [r for r in pool if 2 <= len(r["traits"]) <= 6 and r["category"] in QUESTIONABLE]
    out = []
    for i, r in enumerate(rng.sample(cands, min(n, len(cands)))):
        out.append(_item(
            "lookup_traits", i,
            question=f"List every trait of the Pathfinder 2e {r['category'].replace('-', ' ')} {r['name']}.",
            answer=", ".join(r["traits"]), answer_type="set",
            acceptable=r["traits"], source_ids=[r["id"]], source_urls=[r["url"]],
        ))
    return out


def gen_lookup_rarity(pool: list[dict], rng: random.Random, n: int) -> list[dict]:
    # Uncommon/rare items are the interesting case; common is the majority-class guess.
    cands = [r for r in pool
             if (r["rarity"] or "").lower() not in ("", "common") and r["category"] in QUESTIONABLE]
    out = []
    for i, r in enumerate(rng.sample(cands, min(n, len(cands)))):
        out.append(_item(
            "lookup_rarity", i,
            question=f"What is the rarity of the Pathfinder 2e {r['category'].replace('-', ' ')} {r['name']}?",
            answer=r["rarity"], answer_type="exact", acceptable=[r["rarity"]],
            source_ids=[r["id"]], source_urls=[r["url"]],
        ))
    return out


def gen_prereq(pool: list[dict], rng: random.Random, n: int) -> list[dict]:
    cands = []
    for r in pool:
        if r["category"] != "feat":
            continue
        m = RE_PREREQ.search(r["text"])
        if m:
            prereq = m.group(1).strip().rstrip(".")
            if 3 < len(prereq) < 160:
                cands.append((r, prereq))
    out = []
    for i, (r, prereq) in enumerate(rng.sample(cands, min(n, len(cands)))):
        parts = [p.strip() for p in re.split(r";|,", prereq) if len(p.strip()) > 2]
        out.append(_item(
            "prereq", i,
            question=f"What are the prerequisites for the Pathfinder 2e feat {r['name']}?",
            answer=prereq, answer_type="set", acceptable=parts,
            source_ids=[r["id"]], source_urls=[r["url"]],
        ))
    return out


def _legacy_name(row: dict) -> str | None:
    value = row.get("legacy_name")
    if not value:
        return None
    return value[0] if isinstance(value, list) else value


def gen_remaster_rename(rows: list[dict], rng: random.Random, n: int) -> list[dict]:
    cands = [r for r in rows if r.get("legacy_name") and r["remaster_status"] == "remaster"]

    # Who else claims to be the Remaster version of this legacy name?
    claims: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for r in cands:
        claims[(r["category"], _legacy_name(r).lower())].append(r)
    # Scoped per category: a spell named X does not make an *equipment* question
    # about X false-premised.
    current: set[tuple[str, str]] = {
        (r["category"], r["name"].lower()) for r in rows
        if r["name"] and r["remaster_status"] != "legacy"
    }

    out = []
    for i, r in enumerate(rng.sample(cands, min(n, len(cands)))):
        old = _legacy_name(r)
        if old == r["name"]:
            continue
        siblings = claims[(r["category"], old.lower())]
        item = _item(
            "remaster_rename", i,
            question=(f"The Pathfinder 2e {r['category'].replace('-', ' ')} formerly called "
                      f"{old} was renamed in the Remaster. What is its current name?"),
            answer=r["name"], answer_type="exact",
            acceptable=sorted({s["name"] for s in siblings}),
            must_not_contain=[old],
            source_ids=[r["id"]],
            alt_source_ids=sorted({s["id"] for s in siblings if s["id"] != r["id"]}),
            source_urls=[r["url"]],
        )
        if (r["category"], old.lower()) in current:
            # The premise is false: the "old" name is still a current entry.
            item["excluded"] = True
            item["exclusion_reason"] = f"{old!r} is still a current Pathfinder 2e entry"
        out.append(item)
    return out


def gen_abstention(pool: list[dict], rng: random.Random, n: int) -> list[dict]:
    """Plausible names assembled from real name parts that name nothing real."""
    real = {r["name"].lower() for r in pool if r["name"]}
    feats = [r["name"] for r in pool if r["category"] == "feat" and r["name"] and " " in r["name"]]
    heads = {f.split(" ", 1)[0] for f in feats}
    tails = {f.split(" ", 1)[1] for f in feats}
    heads, tails = sorted(heads), sorted(tails)
    out, seen = [], set()
    while len(out) < n and len(seen) < n * 40:
        name = f"{rng.choice(heads)} {rng.choice(tails)}"
        key = name.lower()
        if key in real or key in seen:
            seen.add(key)
            continue
        seen.add(key)
        out.append(_item(
            "abstention", len(out),
            question=f"In Pathfinder 2e, what level is the feat {name} and what does it do?",
            answer="No such feat exists in Pathfinder 2e.", answer_type="abstain",
            acceptable=["does not exist", "no such feat", "not a Pathfinder 2e feat",
                        "cannot find", "not aware of", "no record"],
            source_ids=[], source_urls=[],
        ))
    return out


def gen_traps(path: pathlib.Path, family: str = "trap_5e") -> list[dict]:
    out = []
    for i, line in enumerate(path.open("rb")):
        seed = orjson.loads(line)
        out.append(_item(
            family, i,
            question=seed["question"], answer=seed["answer"], answer_type="free",
            acceptable=[], must_not_contain=seed.get("must_not_contain", []),
            must_contain=seed.get("must_contain", []),
            topic=seed.get("topic"), wrong_5e_answer=seed.get("wrong_5e_answer"),
            source_ids=[], source_urls=[],
        ))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", type=pathlib.Path, default=ROOT / "data" / "processed" / "aon_chunks.jsonl")
    ap.add_argument("--out", type=pathlib.Path, default=ROOT / "eval" / "benchmark.jsonl")
    ap.add_argument("--per-family", type=int, default=80)
    ap.add_argument("--seed", type=int, default=20260906)
    args = ap.parse_args()

    if not args.chunks.exists():
        print(f"missing {args.chunks}; run scripts/build_chunks.py first", file=sys.stderr)
        return 1

    rows = load(args.chunks)
    # Only ask about current (non-legacy) content, by unambiguous name.
    current = [r for r in rows if r["remaster_status"] != "legacy"]
    pool = list(unique_named(current).values())
    rng = random.Random(args.seed)
    n = args.per_family

    items = (
        gen_lookup_level(pool, rng, n)
        + gen_lookup_traits(pool, rng, n)
        + gen_lookup_rarity(pool, rng, n)
        + gen_prereq(pool, rng, n)
        + gen_remaster_rename(rows, rng, n)
        + gen_abstention(pool, rng, n // 2)
        + gen_traps(ROOT / "eval" / "seeds" / "5e_traps.jsonl")
        + gen_traps(ROOT / "eval" / "seeds" / "5e_traps_applied.jsonl", "trap_5e_applied")
    )

    with args.out.open("wb") as fh:
        for it in items:
            fh.write(orjson.dumps(it))
            fh.write(b"\n")

    counts = collections.Counter(i["family"] for i in items)
    print(f"wrote {len(items)} items -> {args.out}")
    for fam, c in counts.most_common():
        print(f"  {fam:18s} {c:4d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
