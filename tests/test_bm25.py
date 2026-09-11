"""The shipped BM25 against the textbook formula, and its on-disk round trip."""

import math

import numpy as np

from kleverkobold.bm25 import BM25, K1, B

DOCS = [["treat", "wounds", "medicine"], ["treat", "wounds"], ["magic", "missile"],
        ["medicine", "medicine", "check"]]


def _reference(query, docs):
    n = len(docs)
    avg = sum(len(d) for d in docs) / n
    out = []
    for doc in docs:
        score = 0.0
        for term in query:
            df = sum(term in d for d in docs)
            if not df:
                continue
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            tf = doc.count(term)
            score += idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * len(doc) / avg))
        out.append(score)
    return out


def test_scores_match_the_formula():
    bm = BM25.build(DOCS)
    got = bm.scores(["medicine", "treat", "unknownword"])
    want = _reference(["medicine", "treat"], DOCS)
    assert np.allclose(got, want, atol=1e-5)
    assert bm.get_scores(["medicine"]).argmax() == 3   # two occurrences beat one


def test_layout_is_a_sorted_inverted_index():
    bm = BM25.build(DOCS)
    assert list(bm.vocab) == sorted(set(t for d in DOCS for t in d))
    assert bm.n_docs == 4 and bm.indptr[-1] == bm.docs.shape[0]
    i = list(bm.vocab).index("medicine")
    assert list(bm.docs[bm.indptr[i]:bm.indptr[i + 1]]) == [0, 3]
    assert list(bm.tf[bm.indptr[i]:bm.indptr[i + 1]]) == [1, 2]


def test_unknown_terms_and_empty_query_score_zero():
    bm = BM25.build(DOCS)
    assert not bm.scores(["zzz"]).any()
    assert not bm.scores([]).any()


def test_save_and_load_round_trip(tmp_path):
    bm = BM25.build(DOCS)
    path = tmp_path / "bm25.npz"
    bm.save(path)
    again = BM25.load(path)
    assert np.allclose(again.scores(["treat", "medicine"]), bm.scores(["treat", "medicine"]))
    assert again.avg_len == bm.avg_len


def test_empty_corpus_does_not_divide_by_zero():
    bm = BM25.build([[]])
    assert bm.avg_len == 1.0
    assert bm.scores(["x"]).tolist() == [0.0]
