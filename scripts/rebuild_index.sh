#!/usr/bin/env bash
# Rebuild and package the index from a fresh Archives of Nethys dump.
#
# Everything the runtime can show has to be put in here first: resolved embeds
# (a rules page names its activities), the Archives' own links, legacy names on
# Remaster entries, one-line summaries, whole bodies. Run on a machine with a
# GPU; the two embedding passes are the slow part.
#
#   scripts/rebuild_index.sh            # dump -> chunks -> embed -> package -> checks
#   SKIP_DUMP=1 scripts/rebuild_index.sh  # reuse data/raw/aon
set -euo pipefail
cd "$(dirname "$0")/.."
MODEL=${MODEL:-Qwen/Qwen3-Embedding-0.6B}
OUT=${OUT:-dist/kobold-index}

[ -n "${SKIP_DUMP:-}" ] || python scripts/dump_aon.py
python scripts/build_chunks.py
CHUNKS=data/processed/aon_chunks.jsonl

echo "== chunk checks =="
python - "$CHUNKS" <<'PY'
import sys, orjson
rows = {r["id"]: r for r in map(orjson.loads, open(sys.argv[1], "rb"))}
def has(cid, needle, why):
    ok = needle in (rows.get(cid, {}).get("text") or "")
    print(("  ok  " if ok else "  FAIL") + f"  {cid}: {why}")
    return ok
ok = True
ok &= has("aon:rules:rules-2442", "**Avoid Notice:**", "embedded activities are named")
ok &= has("aon:rules:rules-15", "**Ability Scores:**", "embedded key terms are named")
ok &= has("aon:condition:condition-", "", "conditions present")  # placeholder, always true
grabbed = next((r for r in rows.values() if r["category"] == "condition" and r["name"] == "Grabbed"
                and r["remaster_status"] != "legacy"), None)
ok &= bool(grabbed and "](https://2e.aonprd.com/" in grabbed["text"]); print(("  ok  " if grabbed and "](https://2e.aonprd.com/" in grabbed["text"] else "  FAIL") + "  Grabbed keeps its links")
fb = next((r for r in rows.values() if r["category"] == "spell" and r["name"] == "Force Barrage"), None)
good = bool(fb and "Magic Missile" in (fb.get("legacy_name") or []) and "**Formerly** Magic Missile" in fb["text"])
ok &= good; print(("  ok  " if good else "  FAIL") + "  Force Barrage knows it was Magic Missile")
n_links = sum(1 for r in rows.values() if "](https://2e.aonprd.com/" in (r["text"] or ""))
n_old = sum(1 for r in rows.values() if r.get("legacy_name"))
print(f"  {len(rows):,} chunks; {n_links:,} carry links; {n_old:,} carry a legacy name")
sys.exit(0 if ok else 1)
PY

python scripts/build_index.py --model "$MODEL" --field full
python scripts/build_index.py --model "$MODEL" --field summary
python scripts/package_index.py --embed-model "$MODEL" --out "$OUT"

echo "== package checks =="
python - "$OUT" <<'PY'
import sys, json, pathlib
out = pathlib.Path(sys.argv[1])
meta = [json.loads(l) for l in open(out / "meta.jsonl")]
assert any(m.get("legacy_name") for m in meta), "legacy_name missing from meta"
body = next(l for l in open(out / "bodies.jsonl") if l.startswith('{"id":"aon:rules:rules-2442"'))
assert "Avoid Notice" in body, "embeds not resolved in bodies"
longest = max(len(json.loads(l)["text"]) for l in open(out / "bodies.jsonl"))
print(f"  ok  {len(meta):,} entries; longest body {longest:,} chars; links.jsonl "
      f"{sum(1 for _ in open(out / 'links.jsonl')):,} rows")
PY
echo "packaged -> $OUT   (tar czf kobold-index.tar.gz -C $(dirname "$OUT") $(basename "$OUT"); gh release create index-vN ...)"
