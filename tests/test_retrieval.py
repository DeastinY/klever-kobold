"""Tokenising, chunk headers, masks, fusion and the Remaster hop."""

import numpy as np
import pytest

from kleverkobold import retrieval as r
from kleverkobold.bm25 import BM25


def test_tokenize_and_plain():
    assert r.tokenize("Cat Fall's DC-15, level 4!") == ["cat", "fall's", "dc", "15", "level", "4"]
    assert r.plain("see [Grapple](https://x) now") == "see Grapple now"
    assert r.plain(None) == ""


def test_chunk_text_header_carries_the_metadata():
    chunk = {"name": "Force Barrage", "category": "spell", "level": 1, "traits": ["Force"],
             "rarity": "common", "legacy_name": "Magic Missile", "summary": "Darts.",
             "text": "[Body](https://x) text"}
    out = r.chunk_text(chunk)
    head, body = out.split("\n", 1)
    assert head == "Force Barrage | spell | level 1 | Force | common | formerly Magic Missile"
    assert body == "Darts.\nBody text"


def test_chunk_text_lore_flag_and_truncation():
    chunk = {"name": "Cheliax", "category": "nation", "corpus": "pathfinderwiki",
             "text": "x" * 5000}
    out = r.chunk_text(chunk, max_chars=100)
    assert out.startswith("Cheliax | nation | Golarion lore\n")
    assert len(out.split("\n", 1)[1]) <= 100


def _index(rows, **kw):
    ids = [m["id"] for m in rows]
    return r.Index(ids=ids, meta=rows, **kw)


ROWS = [
    {"id": "a", "name": "Treat Wounds", "category": "action", "remaster_status": "unaffected"},
    {"id": "b", "name": "Treat Wounds", "category": "action", "remaster_status": "unaffected"},
    {"id": "c", "name": "Magic Missile", "category": "spell", "remaster_status": "legacy",
     "remaster_id": ["d"]},
    {"id": "aon:spell:d", "name": "Force Barrage", "category": "spell",
     "remaster_status": "remaster"},
    {"id": "w", "name": "Cheliax", "category": "nation", "corpus": "pathfinderwiki"},
    {"id": "n", "name": "", "category": "x"},
]


def test_index_canonical_pools_duplicates_per_corpus():
    idx = _index(ROWS)
    assert idx.canonical[1] == 0          # same name and category
    assert idx.canonical[3] == 3
    assert idx.canonical[5] == 5          # nameless rows stay themselves
    assert idx.has_lore and list(idx.lore_mask) == [False] * 4 + [True, False]
    assert len(idx) == 6 and idx.position("w") == 4 and idx.position("zz") is None


def test_allowed_masks():
    idx = _index(ROWS)
    default = idx.allowed()
    assert list(default) == [True, True, False, True, False, True]
    assert list(idx.allowed(exclude_legacy=False)) == [True, True, True, True, False, True]
    assert list(idx.allowed(lore=True)) == [True, True, False, True, True, True]
    assert list(idx.allowed(categories=["spell"])) == [False, False, False, True, False, False]
    # A category narrowing keeps the wiki in when lore is allowed.
    assert list(idx.allowed(categories=["spell"], lore=True)) == [
        False, False, False, True, True, False]


def test_dense_scores_in_blocks_and_respects_mask():
    vecs = np.eye(6, dtype=np.float16)
    idx = _index(ROWS, embeddings=vecs, summary_embeddings=vecs[::-1].copy())
    q = np.zeros(6, dtype=np.float32)
    q[2] = 1.0
    mask = np.ones(6, dtype=bool)
    assert idx.dense(q, mask, 1, block=2)[0] == 2
    assert idx.dense(q, mask, 1, view="summary")[0] == 3
    mask[2] = False
    assert 2 not in idx.dense(q, mask, 6)
    assert idx.dense(q, np.zeros(6, dtype=bool), 3) == []
    assert _index(ROWS).dense(q, mask, 3) == []


def test_lexical_uses_the_bm25_and_mask():
    docs = [["treat", "wounds"], ["treat", "wounds", "older"], ["magic", "missile"],
            ["force", "barrage"], ["cheliax"], []]
    idx = _index(ROWS, bm25=BM25.build(docs))
    mask = np.ones(6, dtype=bool)
    assert idx.lexical("magic missile", mask, 2)[0] == 2
    mask[2] = False
    assert idx.lexical("magic missile", mask, 6)[0] != 2
    assert _index(ROWS).lexical("x", mask, 3) == []


def test_rrf_plain_and_weighted():
    assert r.rrf([[1, 2, 3], [3, 1, 2]], k=3) == [1, 3, 2]
    # A heavy weight on the second ranking flips the order.
    assert r.rrf([[1, 2], [2, 1]], k=2, weights=[1.0, 5.0]) == [2, 1]
    assert r.rrf([], k=3) == []


def test_rrf_with_index_pools_duplicates_and_returns_best_row():
    idx = _index(ROWS)
    # Rows 0 and 1 are the same entity. Ranked 0 first in one list and 1 first in
    # the other, they pool -- and the row handed back is one that was retrieved
    # at the best rank, not necessarily the canonical.
    fused = r.rrf([[1, 3], [0, 3], [1]], k=3, index=idx)
    assert fused[0] in (0, 1) and 3 in fused and len(fused) == 2


def test_dedupe_keeps_first_seen_row_per_entity():
    idx = _index(ROWS)
    assert r.dedupe(idx, [1, 0, 3, 1]) == [1, 3]
    bare = r.Index(ids=[], meta=[])
    bare.canonical = []
    assert r.dedupe(bare, [2, 2, 1]) == [2, 1]


def test_follow_remaster_hops_legacy_to_its_replacement():
    idx = _index(ROWS)
    assert r.follow_remaster(idx, [2, 0]) == [3, 0]
    # Already there: no duplicate row.
    assert r.follow_remaster(idx, [3, 2]) == [3]
    # A remaster_id that is not in this index keeps the legacy row.
    rows = [dict(ROWS[2], remaster_id="nope")]
    assert r.follow_remaster(_index(rows), [0]) == [0]


def test_search_modes():
    vecs = np.eye(6, dtype=np.float16)
    docs = [["treat", "wounds"], ["treat", "wounds", "older"], ["magic", "missile"],
            ["force", "barrage"], ["cheliax"], ["nothing"]]
    idx = _index(ROWS, embeddings=vecs, summary_embeddings=vecs, bm25=BM25.build(docs))
    q = np.zeros(6, dtype=np.float32)
    q[3] = 1.0
    assert r.search(idx, "force barrage", q, k=1, mode="dense")[0][0] == "aon:spell:d"
    assert r.search(idx, "force barrage", q, k=1, mode="bm25")[0][0] == "aon:spell:d"
    hybrid = r.search(idx, "force barrage", q, k=2)
    assert hybrid[0][0] == "aon:spell:d" and hybrid[0][1]["name"] == "Force Barrage"
    # Lore is masked out unless asked for.
    assert "w" not in [cid for cid, _ in r.search(idx, "cheliax", q, k=6)]
    assert "w" in [cid for cid, _ in r.search(idx, "cheliax", q, k=6, lore=True)]
    with pytest.raises(ValueError):
        r.search(idx, "x", q, mode="sideways")
