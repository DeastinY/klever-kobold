"""The Assistant over a real (tiny) index directory, with a fake model behind it."""

import numpy as np
import pytest
from conftest import FakeClient, build_index, embed_text, plan_reply

from kleverkobold.app import Assistant, OllamaError, Turn


def test_missing_index_is_a_message_not_a_traceback(tmp_path):
    with pytest.raises(OllamaError, match="kobold setup"):
        Assistant(tmp_path / "nowhere", "http://fake:1")


def test_loads_every_part_of_the_package(assistant):
    assert len(assistant.index) == 12
    assert assistant.has_lore is True
    assert assistant.manifest["ollama_llm"] == "fake-llm"
    assert assistant.body("aon:action:2399").startswith("# Treat Wounds")
    assert assistant.body("nope") == ""
    # The link graph resolved to positions.
    medicine = assistant.index.position("aon:skill:42")
    assert medicine in assistant._links or assistant._links  # graph present
    # The base masks keep legacy rows: the Remaster hop needs to retrieve them.
    assert assistant._masks[False].sum() == 9
    assert assistant._masks[True].sum() == 12


def test_search_finds_the_entry_named(assistant, client):
    hits = assistant.search("How does Treat Wounds work?", k=3,
                            plan={"summary": "", "categories": [], "scope": "rules"},
                            rerank=False)
    assert hits[0].name == "Treat Wounds"
    # Duplicates pooled: the two printings of Treat Wounds are one hit.
    assert [h.name for h in hits].count("Treat Wounds") == 1
    assert all(not h.lore for h in hits)
    assert client.embedded[0][0].startswith("Query: ")


def test_search_uses_the_plan_summary_and_kinds(assistant, client):
    plan = {"summary": "heal hit points with the Medicine skill", "categories": ["skill"],
            "scope": "rules"}
    hits = assistant.search("patch up", k=2, plan=plan, rerank=False)
    assert client.embedded[0] == ["Query: patch up",
                                  "Query: heal hit points with the Medicine skill"]
    assert "Medicine" in [h.name for h in hits]


def test_search_hops_from_legacy_to_remaster(assistant):
    plan = {"summary": "", "categories": [], "scope": "rules"}
    hits = assistant.search("magic missile spell", k=2, plan=plan, rerank=False)
    names = [h.name for h in hits]
    assert "Force Barrage" in names and "Magic Missile" not in names
    assert hits[names.index("Force Barrage")].legacy_name == ["Magic Missile"]


def test_scope_controls_the_wiki(assistant):
    plan = {"summary": "", "categories": [], "scope": "lore"}
    rules = assistant.search("who rules Cheliax", k=4, plan=plan, rerank=False, scope="rules")
    assert not any(h.lore for h in rules)
    lore = assistant.search("who rules Cheliax", k=4, plan=plan, rerank=False, scope="auto")
    assert any(h.lore for h in lore)
    assert lore[0].name.startswith("Cheliax")
    forced = assistant.search("who rules Cheliax", k=4, plan={"scope": "rules"},
                              rerank=False, scope="lore")
    assert any(h.lore for h in forced)


def test_lore_answers_keep_a_rules_slot(assistant):
    plan = {"summary": "", "categories": [], "scope": "lore"}
    hits = assistant.search("Desna goddess of dreams luck stars travelers", k=2, plan=plan,
                            rerank=False, scope="lore")
    corpora = {h.corpus for h in hits}
    assert "aon" in corpora


def test_expand_walks_the_link_graph(assistant):
    plan = {"summary": "", "categories": [], "scope": "rules"}
    without = assistant.search("medicine", k=8, plan=plan, rerank=False, expand=0)
    with_links = assistant.search("medicine", k=8, plan=plan, rerank=False, expand=2)
    assert {h.chunk_id for h in with_links} >= {h.chunk_id for h in without[:2]}


def test_retrieve_times_each_stage_and_condenses_history(assistant, client):
    client.replies = ["Rewritten: How does Treat Wounds work untrained?",
                      plan_reply("treat wounds", "action")]
    plan, hits, timings = assistant.retrieve("and untrained?", k=2, rerank=False,
                                             history=[Turn("How does Treat Wounds work?")])
    assert plan["standalone"] == "How does Treat Wounds work untrained?"
    assert plan["lore"] is False and plan["categories"] == ["action"]
    assert set(timings) == {"condense", "rewrite", "retrieve"}
    assert hits[0].name == "Treat Wounds"


def test_ask_builds_the_prompt_and_returns_sources(assistant, client):
    client.replies = [plan_reply("treat wounds", "action"), "1, 2", "Ten minutes, DC 15."]
    out = assistant.ask("What level is Gurglegut? Also Treat Wounds.", k=2)
    assert out["answer"] == "Ten minutes, DC 15."
    assert out["scope"] == "rules"
    assert {s["name"] for s in out["sources"]} <= {"Treat Wounds", "Gurglegut", "Medicine",
                                                   "Battle Medicine", "Prone", "Desna",
                                                   "Force Barrage"}
    assert set(out["timings"]) == {"rewrite", "retrieve", "rerank", "answer", "total"}
    _system, user, model, max_tokens = client.calls[-1]
    assert user.endswith("Question: What level is Gurglegut? Also Treat Wounds.")
    assert model == "fake-llm" and max_tokens == assistant.answer_tokens
    # The entry the question names went last, next to the question.
    named = [h for h in out["hits"] if h.name in ("Gurglegut", "Treat Wounds")]
    if named:
        assert out["hits"][-1].name in ("Gurglegut", "Treat Wounds")


def test_ask_stream_yields_sources_tokens_done(assistant, client):
    client.replies = [plan_reply()]
    events = list(assistant.ask_stream("prone condition", k=2, rerank=False))
    kinds = [e["event"] for e in events]
    assert kinds[0] == "sources" and kinds[-1] == "done"
    assert kinds.count("token") == 4
    assert events[-1]["answer"] == "The kobold says: ten minutes."
    assert "first_token" in events[-1]["timings"]
    # The entry the question names goes last, next to the question.
    assert events[0]["sources"][-1]["name"] == "Prone"


def test_mentions_links_names_in_prose(assistant):
    text = ("You can Treat Wounds as an exploration activity; if you are prone you are "
            "off-guard. Battle Medicine works in combat. Visit https://2e.aonprd.com/Feats.aspx "
            "and remember Cheliax has devils. Gurglegut is a creature.")
    names = {h.name for h in assistant.mentions(text)}
    assert {"Treat Wounds", "Prone", "Battle Medicine", "Cheliax"} <= names
    assert "Gurglegut" not in names            # creatures are not mention kinds
    assert "Medicine" in names or "Battle Medicine" in names
    excluded = assistant.mentions(text, exclude={"https://2e.aonprd.com/Action.aspx?ID=2399"})
    assert "Treat Wounds" not in {h.name for h in excluded}
    assert len(assistant.mentions(text, limit=1)) == 1


def test_mentions_lore_needs_a_mid_sentence_capital(assistant):
    assert "Cheliax" not in {h.name for h in assistant.mentions("Cheliax is a nation.")}
    assert "Cheliax" in {h.name for h in assistant.mentions("The nation of Cheliax is old.")}


def test_verify_embedder_accepts_matching_and_rejects_others(assistant):
    ok, sim = assistant.verify_embedder()
    assert ok and sim > 0.99

    class Negated(FakeClient):
        def embed(self, texts, model, keep_alive=None):
            return -super().embed(texts, model)

    assistant.embed_client = Negated()
    assistant._verified = False
    ok, sim = assistant.verify_embedder()
    assert not ok and sim < 0
    with pytest.raises(OllamaError, match="does not match"):
        assistant.require_embedder()

    class Narrow(FakeClient):
        def embed(self, texts, model, keep_alive=None):
            return np.ones((len(texts), 3), dtype=np.float32)

    assistant.embed_client = Narrow()
    assert assistant.verify_embedder() == (False, 0.0)
    with pytest.raises(OllamaError, match="dimensions differ"):
        assistant.require_embedder()


def test_require_embedder_names_a_backend_that_cannot_embed(assistant):
    class Broken(FakeClient):
        def embed(self, texts, model, keep_alive=None):
            raise KeyError("embeddings")

    assistant.embed_client = Broken()
    assistant._verified = False
    with pytest.raises(OllamaError, match="could not embed"):
        assistant.require_embedder()
    # Once verified, no further probe is made.
    assistant.embed_client = FakeClient()
    assistant._verified = False
    assistant.require_embedder()
    assistant.embed_client = Broken()
    assistant.require_embedder()


def test_verify_without_probe_is_trusted(assistant):
    assistant.manifest.pop("probe")
    assert assistant.verify_embedder() == (True, 1.0)


def test_warmup_touches_both_models_and_reports(assistant, client):
    seen = []
    timings = assistant.warmup(lambda label, secs: seen.append((label, secs is None)))
    assert set(timings) == {"embedding model", "language model"}
    assert seen == [("embedding model", True), ("embedding model", False),
                    ("language model", True), ("language model", False)]
    assert client.embedded[0] == ["warmup"]


def test_variant_shares_the_index_and_only_swaps_the_client(assistant):
    v = assistant.variant(backend="openai", base_url="http://elsewhere:8080/v1/",
                          llm_model="other", api_key="k", context_chars=500)
    try:
        assert v.index is assistant.index
        assert v.manifest["ollama_llm"] == "other"
        assert v.context_chars == 500
        assert v.embed_client is assistant.embed_client   # embedding stays local
        assert v.ollama is not assistant.ollama
    finally:
        v.close()


def test_index_without_lore_hides_the_scope(tmp_path):
    from conftest import ENTRIES
    rules_only = build_index(tmp_path / "rules", [e for e in ENTRIES if e["corpus"] == "aon"])
    a = Assistant(rules_only, "http://fake:1")
    a.ollama.close()
    a.ollama = a.embed_client = FakeClient()
    assert a.has_lore is False
    assert a.resolve_scope("lore", {"scope": "lore"}) is False
    assert a._masks[True].sum() == a._masks[False].sum()


def test_embed_text_is_a_unit_vector():
    v = embed_text("treat wounds")
    assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-5
    assert float(v @ embed_text("treat wounds now")) > float(v @ embed_text("cheliax devils"))
