"""A small BM25 that ships.

``rank_bm25`` keeps the whole tokenised corpus in memory and pickles to 36 MB,
and a pickle is a version-coupled liability in a distributed artifact. This is
the same scoring function over a flat inverted index stored as numpy arrays: it
loads by memory-mapping, scores a query in a few milliseconds, and has no
dependency beyond numpy.

Layout, all parallel arrays in one ``.npz``:
    ``vocab``    term strings, sorted, one per posting list
    ``indptr``   vocab-length + 1 offsets into the postings arrays
    ``docs``     document id per posting
    ``tf``       term frequency per posting
    ``doc_len``  token count per document
"""

from __future__ import annotations

import pathlib
from collections import defaultdict

import numpy as np

K1 = 1.5
B = 0.75


class BM25:
    def __init__(self, vocab: np.ndarray, indptr: np.ndarray, docs: np.ndarray,
                 tf: np.ndarray, doc_len: np.ndarray) -> None:
        self.vocab = vocab
        self.indptr = indptr
        self.docs = docs
        self.tf = tf.astype(np.float32)
        self.doc_len = doc_len.astype(np.float32)
        self.n_docs = len(doc_len)
        self.avg_len = float(self.doc_len.mean()) or 1.0
        # Document frequency per term is just the length of its posting list.
        df = np.diff(indptr).astype(np.float32)
        self.idf = np.log(1.0 + (self.n_docs - df + 0.5) / (df + 0.5)).astype(np.float32)
        self._lookup = {t: i for i, t in enumerate(vocab.tolist())}

    @classmethod
    def build(cls, tokenised: list[list[str]]) -> BM25:
        postings: dict[str, dict[int, int]] = defaultdict(dict)
        doc_len = np.zeros(len(tokenised), dtype=np.int32)
        for doc_id, tokens in enumerate(tokenised):
            doc_len[doc_id] = len(tokens)
            counts = postings
            for token in tokens:
                d = counts[token]
                d[doc_id] = d.get(doc_id, 0) + 1
        vocab = sorted(postings)
        indptr = np.zeros(len(vocab) + 1, dtype=np.int64)
        docs, tf = [], []
        for i, term in enumerate(vocab):
            entries = sorted(postings[term].items())
            indptr[i + 1] = indptr[i] + len(entries)
            docs.extend(d for d, _ in entries)
            tf.extend(c for _, c in entries)
        return cls(np.array(vocab, dtype=object), indptr,
                   np.array(docs, dtype=np.int32), np.array(tf, dtype=np.int32), doc_len)

    def save(self, path: pathlib.Path) -> None:
        np.savez_compressed(
            path, vocab=np.array(self.vocab, dtype=object), indptr=self.indptr,
            docs=self.docs, tf=self.tf.astype(np.int32),
            doc_len=self.doc_len.astype(np.int32))

    @classmethod
    def load(cls, path: pathlib.Path) -> BM25:
        z = np.load(path, allow_pickle=True)
        return cls(z["vocab"], z["indptr"], z["docs"], z["tf"], z["doc_len"])

    def scores(self, query_tokens: list[str]) -> np.ndarray:
        out = np.zeros(self.n_docs, dtype=np.float32)
        norm = K1 * (1.0 - B + B * self.doc_len / self.avg_len)
        for token in query_tokens:
            i = self._lookup.get(token)
            if i is None:
                continue
            lo, hi = self.indptr[i], self.indptr[i + 1]
            docs = self.docs[lo:hi]
            freq = self.tf[lo:hi]
            out[docs] += self.idf[i] * (freq * (K1 + 1.0)) / (freq + norm[docs])
        return out

    # rank_bm25-compatible alias, so the retrieval code does not care which is loaded
    def get_scores(self, query_tokens: list[str]) -> np.ndarray:
        return self.scores(query_tokens)
