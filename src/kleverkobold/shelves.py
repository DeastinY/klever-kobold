"""Extra shelves beside the packaged index: a GM's own notes, searched like the rest.

A shelf is a small directory in the packaged index's own format -- ``meta.jsonl``,
``bodies.jsonl``, ``emb_full.npy``, ``emb_summary.npy``, ``bm25.npz`` and a
``manifest.json`` -- whose rows carry ``"corpus": "campaign"``. It is attached at
startup, after the packaged index has loaded, so nothing is retrained and the
packaged index is never rewritten: rebuilding a shelf takes seconds and
``kobold setup`` fetching a new index leaves it alone.

Shelves are found in ``$KOBOLD_SHELVES`` (paths separated like ``PATH``), or else
every directory under ``<data home>/shelves`` that holds a manifest.

The rows are embedded with the same encoder, through the same server, as queries
are; the packaged vectors are reproduced by Ollama's build of the encoder to a
cosine of 1.000 (checked 2026-09-28), so shelf and index share one space.

Every shelf row is masked out of the ``rules`` and ``lore`` scopes (see
``Index.allowed``); only the ``campaign`` scope sees them, so the measured paths
stay byte-identical. Routing a question to that scope is done by names the shelf
itself lists in its manifest (``triggers``): people, ships and places of the
campaign, plus a few words like "unsere" or "Hausregel". No model call.
"""

from __future__ import annotations

import os
import pathlib
import re
from collections.abc import Callable, Iterable

import numpy as np
import orjson

from . import retrieval
from .bm25 import BM25

SHELF_FILES = ("manifest.json", "meta.jsonl", "bodies.jsonl", "emb_full.npy",
               "emb_summary.npy", "bm25.npz")


def shelf_dirs(data_home: pathlib.Path) -> list[pathlib.Path]:
    env = os.environ.get("KOBOLD_SHELVES")
    if env is not None:
        dirs = [pathlib.Path(p).expanduser() for p in env.split(os.pathsep) if p.strip()]
    else:
        root = data_home / "shelves"
        dirs = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    return [d for d in dirs if (d / "manifest.json").exists()]


class Stacked:
    """Row-wise concatenation of memory-mapped matrices without copying them.

    ``Index.dense`` reads the matrix a block of rows at a time, so all this has
    to offer is ``shape`` and slicing by rows.
    """

    def __init__(self, parts: list[np.ndarray]) -> None:
        self.parts = parts
        self.offsets = np.cumsum([0] + [p.shape[0] for p in parts])
        self.shape = (int(self.offsets[-1]), parts[0].shape[1])
        self.dtype = parts[0].dtype

    def __len__(self) -> int:
        return self.shape[0]

    def __getitem__(self, key: slice) -> np.ndarray:
        start, stop, _ = key.indices(self.shape[0])
        out = []
        for part, lo in zip(self.parts, self.offsets[:-1], strict=False):
            hi = lo + part.shape[0]
            a, b = max(start, lo), min(stop, hi)
            if a < b:
                out.append(np.asarray(part[a - lo:b - lo]))
        return np.concatenate(out) if out else np.empty((0, self.shape[1]), self.dtype)


class SplitBM25:
    """BM25 over the packaged index and each shelf, each part with its own tokenizer.

    Scores from different parts are not on one scale (different vocabularies and
    document counts), which is why the campaign scope ranks each corpus's lexical
    hits separately and lets rank fusion combine them.
    """

    def __init__(self, parts: list[tuple[BM25, Callable[[str], list[str]]]]) -> None:
        self.parts = parts

    def score_text(self, text: str) -> np.ndarray:
        return np.concatenate([bm25.get_scores(tok(text)) for bm25, tok in self.parts])

    def get_scores(self, tokens: list[str]) -> np.ndarray:
        return self.score_text(" ".join(tokens))


class Shelf:
    def __init__(self, path: pathlib.Path) -> None:
        self.path = path
        self.manifest = orjson.loads((path / "manifest.json").read_bytes())
        self.meta = [orjson.loads(line) for line in (path / "meta.jsonl").open("rb")]
        self.full = np.load(path / "emb_full.npy", mmap_mode="r")
        self.summary = np.load(path / "emb_summary.npy", mmap_mode="r")
        self.bm25 = BM25.load(path / "bm25.npz")
        self.tokenize = retrieval.TOKENIZERS[self.manifest.get("tokenizer", "ascii")]
        self.bodies = path / "bodies.jsonl"
        self.preamble = self.manifest.get("preamble") or ""
        self.triggers = [t for t in self.manifest.get("triggers") or [] if t]
        self.name = self.manifest.get("name") or path.name
        self.glossary = {k.lower(): v for k, v in (self.manifest.get("glossary") or {}).items()}


def attach(assistant, data_home: pathlib.Path) -> list[Shelf]:
    """Add every shelf found to an Assistant's already-loaded index."""
    shelves = []
    for path in shelf_dirs(data_home):
        shelf = Shelf(path)
        if shelf.manifest.get("embed_model") != assistant.manifest.get("embed_model"):
            print(f"kobold: shelf {path} was embedded with {shelf.manifest.get('embed_model')}, "
                  f"the index with {assistant.manifest.get('embed_model')}; skipped",
                  file=__import__("sys").stderr)
            continue
        shelves.append(shelf)
    if not shelves:
        return []
    base = assistant.index
    meta = list(base.meta)
    full, summary = [base.embeddings], [base.summary_embeddings]
    parts = [(base.bm25, retrieval.tokenize)]
    for shelf in shelves:
        meta += shelf.meta
        full.append(shelf.full)
        summary.append(shelf.summary)
        parts.append((shelf.bm25, shelf.tokenize))
        offset = 0
        with shelf.bodies.open("rb") as fh:
            for line in fh:
                start = line.index(b'"id":"') + 6
                chunk_id = line[start:line.index(b'"', start)].decode()
                assistant._body_offsets[chunk_id] = (offset, len(line))
                assistant._body_files[chunk_id] = shelf.bodies
                offset += len(line)
    assistant.index = retrieval.Index(
        ids=[m["id"] for m in meta], meta=meta,
        embeddings=Stacked(full), summary_embeddings=Stacked(summary),
        bm25=SplitBM25(parts), model_name=base.model_name)
    return shelves


# --- routing -------------------------------------------------------------------

# Words that make a question about this table rather than about the game.
CUE_WORDS = ("unser", "unsere", "unserer", "unserem", "unseren", "unseres",
             "hausregel", "hausregeln", "house rule", "house rules", "kampagne", "campaign",
             "sitzung", "session", "our ship", "our party", "our crew")


def trigger_pattern(triggers: Iterable[str]) -> re.Pattern | None:
    words = sorted({t.strip().lower() for t in triggers if len(t.strip()) >= 3}, key=len,
                   reverse=True)
    if not words:
        return None
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w) for w in words) + r")(?!\w)")


def compound_hit(question: str, triggers: Iterable[str]) -> bool:
    """German compounds: "Enterkämpfe" contains no trigger as a word, "Hausregel" does."""
    q = question.lower()
    return any(len(t) >= 6 and t.lower() in q for t in triggers)


def expand(question: str, glossary: dict[str, str]) -> list[str]:
    """The glossary's other names for terms the question uses, e.g. Etmal -> Day Speed."""
    return [other for _, other in expand_pairs(question, glossary)]


def expand_pairs(question: str, glossary: dict[str, str]) -> list[tuple[str, str]]:
    """(term, other name) for each glossary term the question uses, at most six."""
    q = question.lower()
    stems = retrieval.tokenize_de(question)
    out = []
    for term, other in glossary.items():
        if len(term) < 3 or other in [o for _, o in out]:
            continue
        hit = re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", q)
        if not hit:
            # German compounds: "Entern" (stem "enter") inside "Enterkämpfe".
            own = retrieval.tokenize_de(term)
            hit = len(own) == 1 and len(own[0]) >= 5 and any(s.startswith(own[0]) for s in stems)
        if hit:
            out.append((term, other))
    return out[:6]


# --- building --------------------------------------------------------------------

def summary_text(row: dict) -> str:
    """Name, kind and one-line summary: the same string build_index.py embeds."""
    head = row.get("name") or ""
    if row.get("category"):
        head += f" ({row['category'].replace('-', ' ')})"
    return f"{head}: {row.get('summary') or ''}".strip()


META_FIELDS = ("id", "corpus", "name", "category", "level", "traits", "rarity", "book",
               "remaster_status", "remaster_id", "legacy_name", "url", "summary",
               "status", "source")


def build(rows: list[dict], out: pathlib.Path, embed: Callable[[list[str]], np.ndarray],
          manifest: dict, batch: int = 32) -> dict:
    """Write a shelf from chunk rows (each with ``id``, ``name``, ``text``, ...).

    ``embed`` takes document texts (no query prefix) and returns unit vectors
    from the encoder that built the packaged index.
    """
    out.mkdir(parents=True, exist_ok=True)
    tokenizer = manifest.setdefault("tokenizer", "unicode-de")
    tok = retrieval.TOKENIZERS[tokenizer]
    full_texts = [retrieval.chunk_text(r) for r in rows]
    sum_texts = [summary_text(r) for r in rows]

    def vecs(texts: list[str]) -> np.ndarray:
        blocks = [np.asarray(embed(texts[i:i + batch]), dtype=np.float32)
                  for i in range(0, len(texts), batch)]
        return np.concatenate(blocks).astype(np.float16)

    tmp = out / ".building"
    tmp.mkdir(exist_ok=True)
    np.save(tmp / "emb_full.npy", vecs(full_texts))
    np.save(tmp / "emb_summary.npy", vecs(sum_texts))
    BM25.build([tok(t) for t in full_texts]).save(tmp / "bm25.npz")
    with (tmp / "meta.jsonl").open("wb") as fh:
        for r in rows:
            fh.write(orjson.dumps({k: r.get(k) for k in META_FIELDS}) + b"\n")
    with (tmp / "bodies.jsonl").open("wb") as fh:
        for r in rows:
            fh.write(orjson.dumps({"id": r["id"], "text": r.get("text") or ""}) + b"\n")
    manifest = {"version": 1, "chunks": len(rows), **manifest}
    (tmp / "manifest.json").write_bytes(orjson.dumps(manifest, option=orjson.OPT_INDENT_2))
    # Swap in whole files only once everything is written, so a running server
    # restarted mid-build never sees half a shelf.
    for name in SHELF_FILES:
        os.replace(tmp / name, out / name)
    tmp.rmdir()
    return manifest
