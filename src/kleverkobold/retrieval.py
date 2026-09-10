"""Hybrid retrieval over the Pathfinder corpus.

Two deliberate choices:

**Entity-granular chunks, never token windows.** Every AoN document is already
one atomic game object with its own metadata. Splitting a feat across two chunks
would be strictly worse than leaving it whole, and stitching several feats into
one window destroys the metadata that makes filtering possible.

**Lexical and dense together.** Rules questions name things exactly ("what level
is Vicious Swing"), which is BM25's home ground, but they also describe things
("the feat that hits harder and leaves you unsteady"), which needs embeddings.
Reciprocal rank fusion combines the two rankings without needing the two scores
to be on a comparable scale.

41,743 chunks is small. Brute-force cosine over a float32 matrix is ~60 MB and a
few milliseconds per query, so there is no vector database here on purpose.

**Two corpora, one index.** Golarion lore from PathfinderWiki sits in the same
matrices as the Archives of Nethys rules, with a ``corpus`` field on every row.
A rules question is answered with the lore masked out, so the measured rules
path is untouched; a lore question sees both, because "who is Desna?" is
answered by the wiki page and the deity's stat block together.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

RE_TOKEN = re.compile(r"[a-z0-9']+")


def tokenize(text: str) -> list[str]:
    return RE_TOKEN.findall(text.lower())


RE_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def plain(text: str) -> str:
    """Body text with markdown links reduced to their labels."""
    return RE_MD_LINK.sub(r"\1", text or "")


def chunk_text(chunk: dict, max_chars: int = 1200) -> str:
    """The string that represents a chunk to the retriever.

    Header first: an entity's name, kind, level and traits are what queries
    actually match on, and putting them ahead of the body keeps them inside the
    embedder's context window even when the body is long.
    """
    head = [chunk.get("name") or ""]
    if chunk.get("category"):
        head.append(chunk["category"].replace("-", " "))
    if chunk.get("level") is not None:
        head.append(f"level {chunk['level']}")
    if chunk.get("traits"):
        head.append(", ".join(chunk["traits"]))
    if chunk.get("rarity"):
        head.append(chunk["rarity"])
    # "Magic Missile" is what the table says; Force Barrage is what the index
    # holds. The old name goes in the header so both views can match it.
    old = chunk.get("legacy_name") or []
    old = [old] if isinstance(old, str) else [n for n in old if n]
    if old:
        head.append("formerly " + ", ".join(old))
    # Lore rows say so in the header: the embedder then has one token that
    # separates "Desna (deity)" the stat block from "Desna" the wiki article.
    if chunk.get("corpus") == "pathfinderwiki":
        head.append("Golarion lore")
    body = (chunk.get("summary") or "") + "\n" + plain(chunk.get("text") or "")
    return " | ".join(h for h in head if h) + "\n" + body[:max_chars].strip()


@dataclass
class Index:
    """A built index: aligned metadata, dense matrix and lexical model."""

    ids: list[str]
    meta: list[dict]
    canonical: list[int] = field(default_factory=list, repr=False)
    lore_mask: np.ndarray | None = field(default=None, repr=False)
    has_lore: bool = False
    embeddings: np.ndarray | None = None
    summary_embeddings: np.ndarray | None = None
    bm25: object | None = None
    model_name: str | None = None
    _by_id: dict[str, int] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._by_id = {cid: i for i, cid in enumerate(self.ids)}
        # Archives of Nethys carries genuine duplicates: an action and its reprint,
        # a creature ability shared by several monsters. Left alone they split an
        # entity's evidence across two rows during rank fusion, so a result that is
        # ranked first by two views can lose to one that is ranked fifth by three.
        # Map every row to a single canonical row per (name, category, corpus).
        # The corpus is part of the key: the Archives' "Desna" (deity) and the
        # wiki's "Desna" (deity) are different documents, and pooling them would
        # let the stat block swallow the lore or the reverse.
        canonical: dict[tuple[str, str, str], int] = {}
        self.canonical = list(range(len(self.ids)))
        for i, meta in enumerate(self.meta):
            key = ((meta.get("name") or "").lower(), meta.get("category") or "",
                   meta.get("corpus") or "aon")
            if not key[0]:
                continue
            self.canonical[i] = canonical.setdefault(key, i)
        # Which rows are lore, once, as a mask: `allowed` is called per query.
        self.lore_mask = np.array([m.get("corpus") == "pathfinderwiki" for m in self.meta],
                                  dtype=bool)
        self.has_lore = bool(self.lore_mask.any())

    def __len__(self) -> int:
        return len(self.ids)

    def position(self, chunk_id: str) -> int | None:
        return self._by_id.get(chunk_id)

    # --- candidate filtering -------------------------------------------------

    def allowed(self, exclude_legacy: bool = True,
                categories: Sequence[str] | None = None,
                lore: bool = False) -> np.ndarray:
        """Boolean mask of chunks a query is allowed to retrieve.

        Legacy entries are excluded by default: they are the pre-Remaster text,
        they are what stale training data already contains, and surfacing them
        as current rules is the exact failure the benchmark measures.

        Lore is excluded by default for the same reason in a different coat: a
        wiki paragraph about the Grab an Edge feat's namesake must never be
        served as its rules text. With ``lore`` the wiki rows are in, and a
        category narrowing keeps them in -- the rewriter's entry kinds are rules
        kinds, and "nation" is not among them.
        """
        mask = np.ones(len(self.ids), dtype=bool)
        if exclude_legacy:
            mask &= np.array([m.get("remaster_status") != "legacy" for m in self.meta])
        if categories:
            wanted = set(categories)
            wanted_mask = np.array([m.get("category") in wanted for m in self.meta])
            mask &= (wanted_mask | self.lore_mask) if lore else wanted_mask
        if not lore:
            mask &= ~self.lore_mask
        return mask

    # --- retrieval -----------------------------------------------------------

    def dense(self, query_vec: np.ndarray, mask: np.ndarray, k: int,
              view: str = "full", block: int = 8192) -> list[int]:
        matrix = self.summary_embeddings if view == "summary" else self.embeddings
        if matrix is None:
            return []
        # Score in blocks. The stored matrix is float16 and memory-mapped; a single
        # `matrix @ query` upcasts all 41,743 rows to float32 at once, which is a
        # 170 MB transient per view and was most of this process's peak memory.
        # Blocking bounds it to a few tens of megabytes at no measurable cost in
        # time, which matters on a 16 GB laptop.
        scores = np.empty(matrix.shape[0], dtype=np.float32)
        for start in range(0, matrix.shape[0], block):
            stop = min(start + block, matrix.shape[0])
            np.dot(np.asarray(matrix[start:stop], dtype=np.float32), query_vec,
                   out=scores[start:stop])
        scores = np.where(mask, scores, -np.inf)
        k = min(k, int(mask.sum()))
        if k <= 0:
            return []
        top = np.argpartition(-scores, k - 1)[:k]
        return list(top[np.argsort(-scores[top])])

    def lexical(self, query: str, mask: np.ndarray, k: int) -> list[int]:
        if self.bm25 is None:
            return []
        scores = np.asarray(self.bm25.get_scores(tokenize(query)))
        scores = np.where(mask, scores, -np.inf)
        k = min(k, int(mask.sum()))
        if k <= 0:
            return []
        top = np.argpartition(-scores, k - 1)[:k]
        return list(top[np.argsort(-scores[top])])


def rrf(rankings: Iterable[Sequence[int]], k: int, smoothing: int = 60,
        weights: Sequence[float] | None = None, index: "Index | None" = None) -> list[int]:
    """Reciprocal rank fusion, optionally weighted per ranking.

    Scores by rank position rather than by score value, so a BM25 score of 31.4
    and a cosine of 0.82 never have to be made commensurable.

    Weights exist because the views are not equally trustworthy on every question
    shape. For a situational question the hypothetical-summary views rank the
    answer first and second while the three question-side views do not find it in
    their top twenty at all -- unweighted fusion lets three noisy rankings outvote
    two good ones.
    """
    rankings = list(rankings)
    if weights is None:
        weights = [1.0] * len(rankings)
    if index is not None:
        # Collapse duplicates inside each ranking first, so an entity accumulates
        # all of its evidence instead of splitting it across identical rows.
        rankings = [dedupe(index, r) for r in rankings]
    # Evidence is pooled per entity (the canonical key), but the row handed back
    # is the best-ranked row that was actually retrieved -- not the canonical
    # row, which is merely the first in the file and for a rules chapter that
    # exists in three books is the legacy Core Rulebook text.
    fused: dict[int, float] = {}
    best: dict[int, tuple[int, int]] = {}
    for ranking, weight in zip(rankings, weights):
        for rank, idx in enumerate(ranking):
            key = index.canonical[idx] if index is not None and index.canonical else idx
            fused[key] = fused.get(key, 0.0) + weight / (smoothing + rank + 1)
            if rank < best.get(key, (rank + 1, idx))[0]:
                best[key] = (rank, idx)
    return [best[key][1] for key, _ in sorted(fused.items(), key=lambda kv: -kv[1])[:k]]


def dedupe(index: "Index", order: Sequence[int]) -> list[int]:
    """Collapse an ordering to one row per entity, keeping the best-ranked.

    The row kept is the one that was retrieved, not the entity's canonical row.
    Returning the canonical row served the legacy Core Rulebook "Exploration
    Activities" in place of the GM Core page that ranked third and actually
    lists the activities: the canonical is the first row in the file, and for
    anything printed in more than one book that is the oldest printing.
    """
    seen: set[int] = set()
    out: list[int] = []
    for i in order:
        c = index.canonical[i] if index.canonical else i
        if c in seen:
            continue
        seen.add(c)
        out.append(i)
    return out


def follow_remaster(index: Index, order: Sequence[int]) -> list[int]:
    """Replace legacy hits with the entries that superseded them.

    Remaster rename questions name the *old* entity, so lexical and dense search
    both land on the legacy chunk -- the one that must not be served as current
    rules. But that chunk stores ``remaster_id`` pointing at its replacement, so
    the right move is to hop rather than to filter: retrieve the legacy entry,
    then hand back the current one. Filtering legacy out up front instead just
    hides the only chunk that knows where the answer went.
    """
    out: list[int] = []
    seen: set[int] = set()
    for idx in order:
        meta = index.meta[idx]
        targets = meta.get("remaster_id") or []
        if isinstance(targets, str):
            targets = [targets]
        hopped = [index.position(f"aon:{meta['category']}:{t}") for t in targets]
        for pos in [p for p in hopped if p is not None] or [idx]:
            if pos not in seen:
                seen.add(pos)
                out.append(pos)
    return out


def search(index: Index, query: str, query_vec: np.ndarray | None, k: int = 5,
           mode: str = "hybrid", pool: int = 50,
           exclude_legacy: bool = True, lore: bool = False) -> list[tuple[str, dict]]:
    mask = index.allowed(exclude_legacy=exclude_legacy, lore=lore)
    if mode == "dense":
        order = index.dense(query_vec, mask, k)
    elif mode == "bm25":
        order = index.lexical(query, mask, k)
    elif mode == "hybrid":
        order = rrf([index.dense(query_vec, mask, pool), index.lexical(query, mask, pool)], k)
    else:  # pragma: no cover
        raise ValueError(f"unknown mode {mode!r}")
    return [(index.ids[i], index.meta[i]) for i in order]
