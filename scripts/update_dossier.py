#!/usr/bin/env python3
"""Regenerate the generated blocks of docs/index.html from what is on disk.

The dossier is the project's public face, so it must never drift from the
artifacts. Everything between a ``<!-- name:start -->`` / ``<!-- name:end -->``
pair is owned by this script; everything else is hand-written prose.

Blocks:
    ``results``   scored eval runs from ``eval/runs/*.scores.json``
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
        report = data["report"]
        meta_path = path.with_name(path.name.replace(".scores.json", ".meta.json"))
        meta = orjson.loads(meta_path.read_bytes()) if meta_path.exists() else {}
        runs.append({"report": report, "meta": meta, "label": report.get("run", path.stem)})
    runs.sort(key=lambda r: -r["report"]["accuracy"])
    return runs


def pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def render_results(runs: list[dict]) -> str:
    if not runs:
        return ('<p class="note">No runs scored yet. Run <code>eval/run_eval.py</code> then '
                '<code>eval/score.py</code>, and <code>scripts/update_dossier.py</code> will fill '
                'this in.</p>')

    head = "".join(f'<th class="num">{SHORT[f]}</th>' for f in FAMILY_ORDER)
    rows = []
    for run in runs:
        fams = run["report"]["families"]
        model = html.escape(run["meta"].get("model", run["label"]))
        cells = "".join(
            f'<td class="num">{pct(fams[f]["accuracy"]) if f in fams else "&mdash;"}</td>'
            for f in FAMILY_ORDER
        )
        rows.append(
            f'<tr><td class="rowname mono">{model}</td>'
            f'<td class="num"><strong>{pct(run["report"]["accuracy"])}</strong></td>{cells}</tr>'
        )

    notes = []
    for run in runs:
        fams = run["report"]["families"]
        model = html.escape(run["meta"].get("model", run["label"]))
        trap = fams.get("trap_5e")
        if trap and "contaminated" in trap:
            notes.append(
                f'<li><strong>{model}</strong> leaked D&amp;D 5e vocabulary into '
                f'{trap["contaminated"]} of {trap["n"]} trap questions.</li>'
            )
        ab = fams.get("abstention")
        if ab and ab.get("fabricated"):
            notes.append(
                f'<li><strong>{model}</strong> invented a level for '
                f'{ab["fabricated"]} of {ab["n"]} feats that do not exist.</li>'
            )
        rn = fams.get("remaster_rename")
        if rn and rn.get("used_legacy_name"):
            notes.append(
                f'<li><strong>{model}</strong> answered with the pre-Remaster name '
                f'{rn["used_legacy_name"]} times out of {rn["n"]}.</li>'
            )

    note_block = f"<ul>{''.join(notes)}</ul>" if notes else ""
    return f"""<div class="scroller">
      <table>
        <thead>
          <tr><th>Model</th><th class="num">overall</th>{head}</tr>
        </thead>
        <tbody>
          {chr(10).join("          " + r for r in rows).strip()}
        </tbody>
        <caption>Closed-book accuracy by family. Every grade is deterministic.</caption>
      </table>
    </div>
    {note_block}"""


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

    tag = f"{len(runs)} run{'s' if len(runs) != 1 else ''} scored" if runs else "no runs scored yet"
    text = re.sub(r'(<span class="tag" id="results-tag">)[^<]*(</span>)',
                  lambda m: m.group(1) + tag + m.group(2), text)

    args.dossier.write_text(text)
    print(f"updated {args.dossier}: {tag}")
    for run in runs:
        print(f"  {run['meta'].get('model', run['label']):28s} {run['report']['accuracy']:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
