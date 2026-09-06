#!/usr/bin/env python3
"""Regenerate the generated blocks of docs/index.html from what is on disk.

The dossier is the project's public face, so it must never drift from the
artifacts. Everything between a ``<!-- name:start -->`` / ``<!-- name:end -->``
pair is owned by this script; everything else is hand-written prose.

Blocks:
    ``results``    scored eval runs from ``eval/runs/*.scores.json``
    ``retrieval``  retriever comparison from ``eval/runs/retrieval.scores.json``
"""

from __future__ import annotations

import argparse
import html
import pathlib
import re

import orjson

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOSSIER = ROOT / "docs" / "index.html"
RUNS = ROOT / "eval" / "runs"

FAMILY_ORDER = [
    "lookup_level", "lookup_traits", "lookup_rarity", "prereq",
    "remaster_rename", "abstention", "trap_5e",
]
SHORT = {
    "lookup_level": "level", "lookup_traits": "traits", "lookup_rarity": "rarity",
    "prereq": "prereq", "remaster_rename": "remaster", "abstention": "abstain",
    "trap_5e": "5e trap",
}


def load_runs() -> list[dict]:
    runs = []
    for path in sorted(RUNS.glob("*.scores.json")):
        data = orjson.loads(path.read_bytes())
        if not isinstance(data, dict) or "report" not in data:
            continue  # retrieval.scores.json has its own shape
        report = data["report"]
        meta_path = path.with_name(path.name.replace(".scores.json", ".meta.json"))
        meta = orjson.loads(meta_path.read_bytes()) if meta_path.exists() else {}
        runs.append({"report": report, "meta": meta, "label": report.get("run", path.stem)})
    runs.sort(key=lambda r: (r["report"].get("partial", False), -r["report"]["accuracy"]))
    return runs


def load_retrieval() -> list[dict]:
    path = RUNS / "retrieval.scores.json"
    if not path.exists():
        return []
    return orjson.loads(path.read_bytes())


def pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def render_results(runs: list[dict]) -> str:
    if not runs:
        return ('<p class="note">No runs scored yet. Run <code>eval/run_eval.py</code> then '
                '<code>eval/score.py</code>, and <code>scripts/update_dossier.py</code> will fill '
                'this in.</p>')

    full = [r for r in runs if not r["report"].get("partial")]
    partial = [r for r in runs if r["report"].get("partial")]

    head = "".join(f'<th class="num">{SHORT[f]}</th>' for f in FAMILY_ORDER)
    rows = []
    for run in full:
        fams = run["report"]["families"]
        model = html.escape(run["meta"].get("model", run["label"]))
        cells = "".join(
            f'<td class="num">{pct(fams[f]["accuracy"]) if f in fams else "&mdash;"}</td>'
            for f in FAMILY_ORDER
        )
        ret = run["meta"].get("retrieval")
        mode = f'+ retrieval (k={ret["k"]})' if ret else "closed-book"
        rows.append(
            f'<tr><td class="rowname mono">{model}</td>'
            f'<td class="mono" style="font-size:0.82rem;color:var(--muted)">{mode}</td>'
            f'<td class="num"><strong>{pct(run["report"]["accuracy"])}</strong></td>{cells}</tr>'
        )

    notes = []
    paired = {}
    for run in full:
        key = run["meta"].get("model", run["label"])
        paired.setdefault(key, {})["rag" if run["meta"].get("retrieval") else "closed"] = run
    for model, pair in paired.items():
        if "closed" in pair and "rag" in pair:
            a = pair["closed"]["report"]["accuracy"]
            b = pair["rag"]["report"]["accuracy"]
            notes.append(
                f'<li><strong>{html.escape(model)}</strong>: {pct(a)} &rarr; {pct(b)} with '
                f'retrieval, {b / a:.1f}&times;.</li>'
            )

    for run in partial:
        fams = run["report"]["families"]
        model = html.escape(run["meta"].get("model", run["label"]))
        kw = run["meta"].get("chat_kwargs") or {}
        detail = ", ".join(f"{k}={v}" for k, v in kw.items()) or "control"
        scored = ", ".join(f"{SHORT[f]} {pct(fams[f]['accuracy'])}" for f in FAMILY_ORDER if f in fams)
        notes.append(f"<li><strong>{model}</strong> control run ({detail}): {scored}.</li>")

    note_block = f"<ul>{''.join(notes)}</ul>" if notes else ""
    return f"""<div class="scroller">
      <table>
        <thead>
          <tr><th>Model</th><th>mode</th><th class="num">overall</th>{head}</tr>
        </thead>
        <tbody>
          {chr(10).join("          " + r for r in rows).strip()}
        </tbody>
        <caption>Closed-book accuracy by family. Every grade is deterministic.</caption>
      </table>
    </div>
    {note_block}"""


def render_retrieval(rows: list[dict]) -> str:
    if not rows:
        return '<p class="note">No retrieval evaluation yet. Run <code>eval/retrieval_eval.py</code>.</p>'
    body = []
    for r in sorted(rows, key=lambda r: -r["recall"]["5"]):
        name = html.escape(r["model"] or "\u2014 (lexical only)")
        body.append(
            f'<tr><td class="rowname mono">{name}</td>'
            f'<td class="mono" style="font-size:0.82rem;color:var(--muted)">{r["mode"]}</td>'
            f'<td class="num">{pct(r["recall"]["1"])}</td>'
            f'<td class="num"><strong>{pct(r["recall"]["5"])}</strong></td>'
            f'<td class="num">{pct(r["recall"]["20"])}</td>'
            f'<td class="num">{r["mrr"]:.3f}</td></tr>'
        )
    return f"""<div class="scroller">
      <table>
        <thead>
          <tr><th>Retriever</th><th>mode</th><th class="num">R@1</th><th class="num">R@5</th><th class="num">R@20</th><th class="num">MRR</th></tr>
        </thead>
        <tbody>
          {chr(10).join("          " + b for b in body).strip()}
        </tbody>
        <caption>Did the right chunk come back? Scored on the 400 benchmark items that carry a gold chunk id. No model involved.</caption>
      </table>
    </div>"""


def replace_block(text: str, name: str, body: str) -> str:
    pattern = re.compile(
        rf"(<!-- {name}:start -->)(.*?)(<!-- {name}:end -->)", re.S
    )
    if not pattern.search(text):
        raise SystemExit(f"no <!-- {name}:start --> block in {DOSSIER}")
    return pattern.sub(lambda m: f"{m.group(1)}\n    {body}\n    {m.group(3)}", text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dossier", type=pathlib.Path, default=DOSSIER)
    args = ap.parse_args()

    runs = load_runs()
    text = args.dossier.read_text()
    text = replace_block(text, "results", render_results(runs))
    text = replace_block(text, "retrieval", render_retrieval(load_retrieval()))

    n_full = sum(1 for r in runs if not r["report"].get("partial"))
    tag = f"{n_full} run{'s' if n_full != 1 else ''} scored" if runs else "no runs scored yet"
    text = re.sub(r'(<span class="tag" id="results-tag">)[^<]*(</span>)',
                  lambda m: m.group(1) + tag + m.group(2), text)

    args.dossier.write_text(text)
    print(f"updated {args.dossier}: {tag}")
    for run in runs:
        kind = "control" if run["report"].get("partial") else "        "
        print(f"  {kind} {run['meta'].get('model', run['label']):26s} {run['report']['accuracy']:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
