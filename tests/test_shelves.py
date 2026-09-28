"""Shelves: a GM's own notes attached beside the packaged index."""

import numpy as np

from kleverkobold import retrieval, shelves
from kleverkobold.bm25 import BM25


def test_german_tokenizer_meets_compounds_and_umlauts():
    assert retrieval.tokenize_de("Enterkämpfe") == retrieval.tokenize_de("Enterkampf")
    assert retrieval.tokenize_de("Größe") == retrieval.tokenize_de("Grosse") == ["gross"]


def test_stacked_and_split_bm25_line_up_rows():
    a, b = np.arange(12, dtype=np.float16).reshape(6, 2), np.ones((3, 2), dtype=np.float16)
    stacked = shelves.Stacked([a, b])
    assert stacked.shape == (9, 2)
    assert np.array_equal(stacked[4:8], np.concatenate([a[4:], b[:2]]))
    base = BM25.build([retrieval.tokenize("grab an edge")])
    shelf = BM25.build([retrieval.tokenize_de("Hausregel für Enterkämpfe")])
    scores = shelves.SplitBM25([(base, retrieval.tokenize),
                                (shelf, retrieval.tokenize_de)]).score_text("Enterkampf")
    assert scores.shape == (2,) and scores[0] == 0 and scores[1] > 0


def test_campaign_rows_stay_out_of_rules_and_lore():
    meta = [{"id": "aon:1", "name": "Grapple", "corpus": "aon"},
            {"id": "wiki:1", "name": "Cheliax", "corpus": "pathfinderwiki"},
            {"id": "campaign:1", "name": "Miro", "corpus": "campaign"}]
    index = retrieval.Index(ids=[m["id"] for m in meta], meta=meta)
    assert index.allowed().tolist() == [True, False, False]
    assert index.allowed(lore=True).tolist() == [True, True, False]
    assert index.allowed(campaign=True).tolist() == [True, False, True]


def test_routing_by_trigger_and_glossary_expansion():
    pattern = shelves.trigger_pattern(["Miro", "Schatzinsel", *shelves.CUE_WORDS])
    assert pattern.search("wer ist miro?")
    assert pattern.search("was ist das etmal unserer pinasse?")
    assert not pattern.search("how does treat wounds work?")
    glossary = {"etmal": "Day Speed", "entern": "boarding"}
    assert shelves.expand("Was ist das Etmal?", glossary) == ["Day Speed"]
    assert shelves.expand("Welche Hausregel gilt für Enterkämpfe?", glossary) == ["boarding"]
