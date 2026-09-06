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
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np

RE_TOKEN = re.compile(r"[a-z0-9']+")


def tokenize(text: str) -> list[str]:
    return RE_TOKEN.findall(text.lower())


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
    body = (chunk.get("summary") or "") + "\n" + (chunk.get("text") or "")
    return " | ".join(h for h in head if h) + "\n" + body[:max_chars].strip()


@dataclass
class Index:
    """A built index: aligned metadata, dense matrix and lexical model."""

    ids: list[str]
    meta: list[dict]
    canonical: list[int] = field(default_factory=list, repr=False)
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
        # Map every row to a single canonical row per (name, category).
        canonical: dict[tuple[str, str], int] = {}
        self.canonical = list(range(len(self.ids)))
        for i, meta in enumerate(self.meta):
            key = ((meta.get("name") or "").lower(), meta.get("category") or "")
            if not key[0]:
                continue
            self.canonical[i] = canonical.setdefault(key, i)

    def __len__(self) -> int:
        return len(self.ids)

    def position(self, chunk_id: str) -> int | None:
        return self._by_id.get(chunk_id)

    # --- candidate filtering -------------------------------------------------

    def allowed(self, exclude_legacy: bool = True,
                categories: Sequence[str] | None = None) -> np.ndarray:
        """Boolean mask of chunks a query is allowed to retrieve.

        Legacy entries are excluded by default: they are the pre-Remaster text,
        they are what stale training data already contains, and surfacing them
        as current rules is the exact failure the benchmark measures.
        """
        mask = np.ones(len(self.ids), dtype=bool)
        if exclude_legacy:
            mask &= np.array([m.get("remaster_status") != "legacy" for m in self.meta])
        if categories:
            wanted = set(categories)
            mask &= np.array([m.get("category") in wanted for m in self.meta])
        return mask

    # --- retrieval -----------------------------------------------------------

    def dense(self, query_vec: np.ndarray, mask: np.ndarray, k: int,
              view: str = "full") -> list[int]:
        matrix = self.summary_embeddings if view == "summary" else self.embeddings
        if matrix is None:
            return []
        scores = matrix @ query_vec
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
    fused: dict[int, float] = {}
    for ranking, weight in zip(rankings, weights):
        for rank, idx in enumerate(ranking):
            fused[idx] = fused.get(idx, 0.0) + weight / (smoothing + rank + 1)
    return [i for i, _ in sorted(fused.items(), key=lambda kv: -kv[1])[:k]]


def dedupe(index: "Index", order: Sequence[int]) -> list[int]:
    """Collapse an ordering to one row per entity, keeping the best-ranked."""
    seen: set[int] = set()
    out: list[int] = []
    for i in order:
        c = index.canonical[i] if index.canonical else i
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
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
           exclude_legacy: bool = True) -> list[tuple[str, dict]]:
    mask = index.allowed(exclude_legacy=exclude_legacy)
    if mode == "dense":
        order = index.dense(query_vec, mask, k)
    elif mode == "bm25":
        order = index.lexical(query, mask, k)
    elif mode == "hybrid":
        order = rrf([index.dense(query_vec, mask, pool), index.lexical(query, mask, pool)], k)
    else:  # pragma: no cover
        raise ValueError(f"unknown mode {mode!r}")
    return [(index.ids[i], index.meta[i]) for i in order]
