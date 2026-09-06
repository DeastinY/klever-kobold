#!/usr/bin/env python3
"""Generate RAFT training data: questions, retrieved context, grounded answers.

Phase 2 established what the adapter actually has to learn, and it is not what
the project set out to teach. Retrieval already removed the D&D 5e prior. What
survived is two behaviours:

    precision   the gold chunk is in the context and the model answers from a
                different one -- ``prereq`` retrieves at 100% R@5 and scores 21%
    abstention  retrieval *created* this failure. Handed five plausible
                neighbours, models answer about a neighbour rather than saying
                the asked-for thing was never written

So every training item puts one gold chunk among hard distractors -- the
retriever's own top hits for that question, which is what makes them hard -- and
the answer uses exactly one of them and cites it. Three families exist purely to
teach refusal: invented entity names, and real entities whose gold chunk has been
deliberately withheld from the context.

Answers are generated from the corpus's structured fields rather than distilled
from a teacher model. For these two behaviours that is a feature: the supervision
is exactly correct by construction, free, and reproducible. Phrasing is varied
across several templates per family so the adapter learns the behaviour rather
than a sentence.

**Hygiene:** every entity named by a benchmark item is excluded, and so is every
chunk any benchmark item cites. Nothing in the test set contributes a training
example.
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
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "eval"))

RE_PREREQ = re.compile(r"\*\*Prerequisites?\*\*\s*(.+)")

QUESTIONABLE = {
    "feat", "spell", "action", "creature", "equipment", "weapon", "armor",
    "shield", "hazard", "ritual", "background", "archetype", "heritage",
    "class-feature", "condition", "trait", "deity", "relic",
}

# Several phrasings per family so the adapter learns the behaviour, not a sentence.
SAY_LEVEL = [
    "{name} is a level {level} {kind}. (Source: {url})",
    "Level {level}. {name} is a {kind} at that level. (Source: {url})",
    "{name} is {ordinal} level. (Source: {url})",
]
SAY_TRAITS = [
    "{name} has the traits {traits}. (Source: {url})",
    "The traits on {name} are {traits}, and no others. (Source: {url})",
    "{traits}. Those are the complete traits for {name}. (Source: {url})",
]
SAY_RARITY = [
    "{name} is {rarity}. (Source: {url})",
    "Its rarity is {rarity}. (Source: {url})",
]
SAY_PREREQ = [
    "{name} requires {prereq}. (Source: {url})",
    "The prerequisites for {name} are {prereq}, and nothing else. (Source: {url})",
    "{prereq}. (Source: {url})",
]
SAY_RENAME = [
    "It is now called {name}. (Source: {url})",
    "{old} was renamed to {name} in the Remaster. (Source: {url})",
    "The current name is {name}. (Source: {url})",
]
SAY_ABSENT = [
    "There is no Pathfinder 2e {kind} called {name}. Nothing in the excerpts provided "
    "matches that name, and I have no record of it.",
    "{name} does not exist in Pathfinder 2e as far as I can tell. The excerpts cover other "
    "{kind}s, none of which is the one you asked about.",
    "I can't find a {kind} named {name}. The provided excerpts do not contain it.",
]
SAY_NOT_IN_CONTEXT = [
    "The excerpts provided do not include {name}, so I can't give you its {attribute} from "
    "them. They cover other entries instead.",
    "{name} isn't among the excerpts here. I'd need its entry to answer that.",
    "None of the provided excerpts is {name}, so I can't confirm its {attribute}.",
]


def render(rng: random.Random, templates: list[str], **kw) -> str:
    return rng.choice(templates).format(**kw)


def ordinal(n: int) -> str:
    """1 -> 1st. Naive "{n}th" produced "1th level" in the first training set, and
    the adapter faithfully learned to say it."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def noun(category: str) -> str:
    return category.replace("-", " ")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "aon_chunks.jsonl")
    ap.add_argument("--benchmark", type=pathlib.Path, default=ROOT / "eval" / "benchmark.jsonl")
    ap.add_argument("--out", type=pathlib.Path,
                    default=ROOT / "data" / "processed" / "raft_train.jsonl")
    ap.add_argument("--retriever", default="Kaylebor/pf2e-codex-embed-xs")
    ap.add_argument("--k", type=int, default=5, help="excerpts per item, matching eval")
    ap.add_argument("--per-family", type=int, default=520)
    ap.add_argument("--context-chars", type=int, default=1600)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    from pf2etune import retrieval as R
    import retrieval_eval
    from run_eval import SYSTEM_RAG, format_context

    rows = [orjson.loads(l) for l in args.chunks.open("rb")]
    by_id = {r["id"]: r for r in rows}
    bodies = {r["id"]: r["text"] for r in rows}

    # --- hygiene: nothing the benchmark touches may produce a training item ---
    bench = [orjson.loads(l) for l in args.benchmark.open("rb")]
    # Alternates count: a benchmark item that accepts several Remaster names must
    # not have any of those entities appear as a training gold.
    banned_ids = {sid for item in bench
                  for sid in item["source_ids"] + (item.get("alt_source_ids") or [])}
    banned_names = {by_id[i]["name"].lower() for i in banned_ids if i in by_id}
    print(f"excluded {len(banned_ids)} benchmark chunks / {len(banned_names)} names")

    counts = collections.Counter(r["name"] for r in rows if r["name"])
    pool = [r for r in rows
            if r["name"] and counts[r["name"]] == 1
            and r["id"] not in banned_ids and r["name"].lower() not in banned_names
            and r["remaster_status"] != "legacy" and r["category"] in QUESTIONABLE]
    print(f"{len(pool):,} eligible entities")

    rng = random.Random(args.seed)
    index = retrieval_eval.load_index(args.retriever)
    mask = index.allowed(exclude_legacy=False)

    # --- build the question list first, so retrieval runs in one batch ---------
    specs: list[dict] = []

    def take(pred, n, kind):
        cands = [r for r in pool if pred(r)]
        rng.shuffle(cands)
        for r in cands[:n]:
            specs.append({"kind": kind, "chunk": r})

    take(lambda r: r["level"] is not None, args.per_family, "level")
    take(lambda r: 2 <= len(r["traits"]) <= 6, args.per_family, "traits")
    take(lambda r: (r["rarity"] or "").lower() not in ("", "common"), args.per_family // 2, "rarity")
    take(lambda r: r["category"] == "feat" and RE_PREREQ.search(r["text"]), args.per_family, "prereq")

    # Skip renames AoN records ambiguously: "Tanglefoot Bag" maps to Glue Bomb and
    # all four of its grades, and training the adapter to pick one grade teaches a
    # coin flip. Also skip names that are still live entries, where the premise of
    # the question is false.
    claims: collections.Counter = collections.Counter()
    for r in rows:
        if r["remaster_status"] == "remaster" and r.get("legacy_name"):
            old = r["legacy_name"][0] if isinstance(r["legacy_name"], list) else r["legacy_name"]
            claims[(r["category"], old.lower())] += 1
    live = {(r["category"], r["name"].lower()) for r in rows
            if r["name"] and r["remaster_status"] != "legacy"}

    def unambiguous(r: dict) -> bool:
        old = r["legacy_name"][0] if isinstance(r["legacy_name"], list) else r["legacy_name"]
        key = (r["category"], old.lower())
        return claims[key] == 1 and key not in live

    renames = [r for r in rows if r.get("legacy_name") and r["remaster_status"] == "remaster"
               and r["id"] not in banned_ids and unambiguous(r)]
    rng.shuffle(renames)
    for r in renames[:args.per_family // 2]:
        specs.append({"kind": "rename", "chunk": r})

    # Withheld: a real entity whose own chunk is removed from the context.
    take(lambda r: r["level"] is not None, args.per_family // 2, "withheld")

    # Invented: a plausible name assembled from real parts that names nothing.
    real = {r["name"].lower() for r in rows if r["name"]}
    feats = [r["name"] for r in pool if r["category"] == "feat" and " " in r["name"]]
    heads = sorted({f.split(" ", 1)[0] for f in feats})
    tails = sorted({f.split(" ", 1)[1] for f in feats})
    seen: set[str] = set()
    while sum(1 for s in specs if s["kind"] == "invented") < args.per_family // 2:
        name = f"{rng.choice(heads)} {rng.choice(tails)}"
        if name.lower() in real or name.lower() in seen:
            continue
        seen.add(name.lower())
        specs.append({"kind": "invented", "chunk": None, "name": name})

    # --- questions -------------------------------------------------------------
    for spec in specs:
        c, kind = spec["chunk"], spec["kind"]
        if kind == "level":
            spec["question"] = f"In Pathfinder 2e, what level is the {noun(c['category'])} {c['name']}?"
        elif kind == "traits":
            spec["question"] = f"List every trait of the Pathfinder 2e {noun(c['category'])} {c['name']}."
        elif kind == "rarity":
            spec["question"] = f"What is the rarity of the Pathfinder 2e {noun(c['category'])} {c['name']}?"
        elif kind == "prereq":
            spec["question"] = f"What are the prerequisites for the Pathfinder 2e feat {c['name']}?"
        elif kind == "rename":
            old = c["legacy_name"][0] if isinstance(c["legacy_name"], list) else c["legacy_name"]
            spec["old"] = old
            spec["question"] = (f"The Pathfinder 2e {noun(c['category'])} formerly called {old} was "
                                f"renamed in the Remaster. What is its current name?")
        elif kind == "withheld":
            spec["question"] = f"In Pathfinder 2e, what level is the {noun(c['category'])} {c['name']}?"
        else:
            spec["question"] = (f"In Pathfinder 2e, what level is the feat {spec['name']} and "
                                f"what does it do?")

    print(f"{len(specs)} items; retrieving {args.k} excerpts each")
    qvecs = retrieval_eval.encode_queries(args.retriever, [s["question"] for s in specs])

    out: list[dict] = []
    for spec, qvec in zip(specs, qvecs):
        order = R.rrf([index.dense(qvec, mask, 50),
                       index.lexical(spec["question"], mask, 50)], args.k * 4)
        order = R.follow_remaster(index, order)
        gold_id = spec["chunk"]["id"] if spec["chunk"] else None

        picked = [i for i in order if index.ids[i] != gold_id][: args.k - 1]
        if spec["kind"] in ("withheld", "invented"):
            # No gold in context: every excerpt is a distractor, on purpose.
            picked = [i for i in order if index.ids[i] != gold_id][: args.k]
        elif gold_id is not None:
            gold_pos = index.position(gold_id)
            if gold_pos is None:
                continue
            slot = rng.randrange(len(picked) + 1)  # gold anywhere, not always first
            picked.insert(slot, gold_pos)

        hits = [(index.ids[i], index.meta[i]) for i in picked]
        context = format_context(hits, bodies, args.context_chars)

        c = spec["chunk"]
        kind = spec["kind"]
        if kind == "level":
            answer = render(rng, SAY_LEVEL, name=c["name"], level=c["level"],
                            ordinal=ordinal(int(c["level"])),
                            kind=noun(c["category"]), url=c["url"])
        elif kind == "traits":
            answer = render(rng, SAY_TRAITS, name=c["name"],
                            traits=", ".join(c["traits"]), url=c["url"])
        elif kind == "rarity":
            answer = render(rng, SAY_RARITY, name=c["name"], rarity=c["rarity"], url=c["url"])
        elif kind == "prereq":
            prereq = RE_PREREQ.search(c["text"]).group(1).strip().rstrip(".")
            answer = render(rng, SAY_PREREQ, name=c["name"], prereq=prereq, url=c["url"])
        elif kind == "rename":
            answer = render(rng, SAY_RENAME, name=c["name"], old=spec["old"], url=c["url"])
        elif kind == "withheld":
            answer = render(rng, SAY_NOT_IN_CONTEXT, name=c["name"], attribute="level")
        else:
            answer = render(rng, SAY_ABSENT, name=spec["name"], kind="feat")

        out.append({
            "kind": kind,
            "question": spec["question"],
            "messages": [
                {"role": "system", "content": SYSTEM_RAG},
                {"role": "user", "content": context + "\n\nQuestion: " + spec["question"]},
                {"role": "assistant", "content": answer},
            ],
            "gold_id": gold_id,
            "context_ids": [h[0] for h in hits],
        })

    rng.shuffle(out)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("wb") as fh:
        for row in out:
            fh.write(orjson.dumps(row))
            fh.write(b"\n")

    kinds = collections.Counter(r["kind"] for r in out)
    chars = sum(len(m["content"]) for r in out for m in r["messages"])
    print(f"\nwrote {len(out):,} items -> {args.out}")
    for k, v in kinds.most_common():
        print(f"  {k:12s} {v:5d}")
    print(f"  ~{chars / 4 / 1e6:.1f} M tokens total, {chars / len(out) / 4:.0f} per item")
    refusals = kinds["withheld"] + kinds["invented"]
    print(f"  {refusals / len(out):.0%} of items teach refusal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
