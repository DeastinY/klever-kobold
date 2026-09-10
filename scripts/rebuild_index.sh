#!/usr/bin/env bash
# Rebuild and package the index from fresh Archives of Nethys and PathfinderWiki dumps.
#
# Everything the runtime can show has to be put in here first: resolved embeds
# (a rules page names its activities), the Archives' own links, legacy names on
# Remaster entries, one-line summaries, whole bodies, and the lore -- one chunk
# per wiki article or section, with the infobox written in as facts. Run on a
# machine with a GPU; the two embedding passes are the slow part.
#
#   scripts/rebuild_index.sh              # dump -> chunks -> embed -> package -> checks
#   SKIP_DUMP=1 scripts/rebuild_index.sh  # reuse data/raw/aon and data/raw/wiki
#   NO_LORE=1 scripts/rebuild_index.sh    # rules only, the index-v2 shape
set -euo pipefail
cd "$(dirname "$0")/.."
MODEL=${MODEL:-Qwen/Qwen3-Embedding-0.6B}
OUT=${OUT:-dist/kobold-index}
# 256 needs the whole card to itself; 64 fits beside a running Ollama.
BATCH=${BATCH:-64}
export PYTORCH_CUDA_ALLOC_CONF=${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}

[ -n "${SKIP_DUMP:-}" ] || python scripts/dump_aon.py
python scripts/build_chunks.py
CHUNKS=data/processed/aon_chunks.jsonl
# The rules file goes first: on a shared name the runtime prefers the earlier row.
ALL_CHUNKS="$CHUNKS"
if [ -z "${NO_LORE:-}" ]; then
  [ -n "${SKIP_DUMP:-}" ] || python scripts/dump_wiki.py
  python scripts/build_wiki_chunks.py
  ALL_CHUNKS="$CHUNKS data/processed/wiki_chunks.jsonl"
fi

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

if [ -z "${NO_LORE:-}" ]; then
echo "== lore chunk checks =="
python - data/processed/wiki_chunks.jsonl <<'PY'
import sys, orjson
rows = [orjson.loads(l) for l in open(sys.argv[1], "rb")]
by_name = {r["name"]: r for r in rows}
ok = True
def check(cond, why):
    global ok
    ok &= bool(cond); print(("  ok  " if cond else "  FAIL") + "  " + why)
check(all(r.get("corpus") == "pathfinderwiki" for r in rows), "every lore row carries its corpus")
lead = by_name.get("Cheliax")
check(lead and "**Capital**" in lead["text"], "Cheliax carries its infobox as facts")
check(any(r["name"].startswith("Cheliax › ") for r in rows), "Cheliax is split into sections")
check(sum(1 for r in rows if not r.get("summary")) < len(rows) * 0.02,
      "lore rows have a one-line summary for the summary index")
leftover = sum(1 for r in rows if "{{" in (r["text"] or "") or "[[" in (r["text"] or "") or "{|" in (r["text"] or ""))
check(leftover < len(rows) * 0.002, f"wikitext left in {leftover:,} rows (allowed: a few unbalanced pages)")
sections = sum(1 for r in rows if r.get("section"))
print(f"  {len(rows):,} lore chunks, {sections:,} of them sections")
sys.exit(0 if ok else 1)
PY
fi

python scripts/build_index.py --model "$MODEL" --field full --chunks $ALL_CHUNKS --batch-size "$BATCH"
python scripts/build_index.py --model "$MODEL" --field summary --chunks $ALL_CHUNKS --batch-size "$BATCH"
python scripts/package_index.py --embed-model "$MODEL" --out "$OUT" --chunks $ALL_CHUNKS

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
manifest = json.load(open(out / "manifest.json"))
lore = sum(1 for m in meta if m.get("corpus") == "pathfinderwiki")
assert lore == manifest.get("chunks_by_corpus", {}).get("pathfinderwiki", 0), "lore count drifted"
print(f"  ok  {lore:,} lore rows; manifest says {manifest.get('chunks_by_corpus')}")
PY
echo "packaged -> $OUT   (tar czf kobold-index.tar.gz -C $(dirname "$OUT") $(basename "$OUT"); gh release create index-vN ...)"
