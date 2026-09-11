"""The pure parts of the pipeline: plans, prompts, ordering rules, scope."""

import pytest

from kleverkobold.app import (
    ANSWER_SYSTEM,
    FOLLOWUP_NOTE,
    LORE_ANSWER_SYSTEM,
    RULES_SLOTS,
    Assistant,
    Hit,
    OllamaError,
    Turn,
    parse_plan,
    stat_block_first,
)


def hit(cid, name, corpus="aon", category="feat", level=None, text="body", summary=""):
    return Hit(chunk_id=cid, name=name, category=category, level=level,
               url=f"https://x/{cid}", text=text, summary=summary, corpus=corpus)


@pytest.mark.parametrize("raw, want", [
    ("SUMMARY: heal in ten minutes\nKINDS: action, spell\nSCOPE: rules",
     {"summary": "heal in ten minutes", "categories": ["action", "spell"], "scope": "rules"}),
    ("summary: - Cat Fall.\nkinds: Feat, feat, class feature, dragon\nscope: Lore.",
     {"summary": "Cat Fall.", "categories": ["feat", "class-feature"], "scope": "lore"}),
    ("KINDS: a, b, c, d, feat, spell, action, condition", {"summary": "",
     "categories": ["feat", "spell", "action"], "scope": "rules"}),
    ("SCOPE: probably lore", {"summary": "", "categories": [], "scope": "rules"}),
    ("", {"summary": "", "categories": [], "scope": "rules"}),
    (None, {"summary": "", "categories": [], "scope": "rules"}),
])
def test_parse_plan(raw, want):
    assert parse_plan(raw) == want


def test_parse_plan_caps_summary_length():
    assert len(parse_plan("SUMMARY: " + "x" * 500)["summary"]) == 220


def test_hit_and_turn():
    assert hit("a", "A").lore is False
    assert hit("b", "B", corpus="pathfinderwiki").lore is True
    assert Turn(question="q").asked() == "q"
    assert Turn(question="q", standalone="s").asked() == "s"


def bare(context_chars=1600):
    a = Assistant.__new__(Assistant)
    a.context_chars = context_chars
    a.manifest = {"ollama_llm": "m"}
    return a


def test_context_headers_and_tags():
    a = bare(context_chars=20)
    rules = [hit("a", "Treat Wounds", category="action", text="[link](https://x) " + "x" * 50)]
    out = a.context(rules)
    assert out.startswith("<rules_excerpts>\n[1] Treat Wounds (action) — https://x/a\nlink xxx")
    assert out.endswith("</rules_excerpts>")
    assert len(out.split("\n")[2]) <= 20
    lore = [*rules, hit("w", "Cheliax", corpus="pathfinderwiki", category="nation",
                        text="Nethys Note: nothing\nDevils.")]
    out = a.context(lore)
    assert out.startswith("<excerpts>") and "Golarion lore from PathfinderWiki" in out
    assert "Nethys Note" not in out and "Devils." in out
    levelled = a.context([hit("c", "Gurglegut", category="creature", level=12)])
    assert "(creature, level 12)" in levelled


def test_system_prompt_choice():
    a = bare()
    rules = [hit("a", "A")]
    lore = [hit("w", "W", corpus="pathfinderwiki")]
    assert a.answer_system(None, rules) == ANSWER_SYSTEM
    assert a.answer_system(None, lore) == LORE_ANSWER_SYSTEM
    assert a.answer_system([Turn("q")], rules) == ANSWER_SYSTEM + FOLLOWUP_NOTE
    assert Assistant.system_for([]) == ANSWER_SYSTEM


def test_prompt_puts_history_before_excerpts():
    a = bare()
    turn = Turn(question="How does Treat Wounds work?", answer="Ten minutes.")
    out = a.prompt("and untrained?", [hit("a", "A")], [turn])
    assert out.startswith("<earlier_exchange>\nQuestion: How does Treat Wounds work?\n"
                          "Answer: Ten minutes.\n</earlier_exchange>\n\n<rules_excerpts>")
    assert out.endswith("\n\nQuestion: and untrained?")
    assert a.earlier(None) == "" and a.earlier([]) == ""
    assert "Answer:" not in a.earlier([Turn("q")])


def test_named_last_moves_named_entries_to_the_end():
    hits = [hit("g", "Gurglegut"), hit("a", "Aid"), hit("t", "Treat Wounds")]
    out = Assistant.named_last("what level is gurglegut? not aid", hits)
    assert [h.chunk_id for h in out] == ["a", "t", "g"]      # "Aid" is under four characters
    assert Assistant.named_last("nothing named", hits) == hits


def test_keep_rules_reserves_slots_for_the_archives():
    lore = [hit(f"w{i}", f"Page {i}", corpus="pathfinderwiki") for i in range(4)]
    rules = [hit("r1", "Rule 1"), hit("r2", "Rule 2"), hit("r3", "Rule 3")]
    # Already enough rules: untouched.
    top = lore[:2] + rules[:2]
    assert Assistant.keep_rules(top, top + rules, 4) == top
    # No rules candidate at all: untouched.
    assert Assistant.keep_rules(lore, lore, 4) == lore
    # Otherwise the last lore rows make room and the rules go at the end.
    out = Assistant.keep_rules(lore, lore + rules, 4)
    assert [h.chunk_id for h in out] == ["w0", "w1", "r1", "r2"]
    assert RULES_SLOTS == 2
    # One rule present: only one slot to fill, taken from candidates not already shown.
    top = [lore[0], rules[0], lore[1], lore[2]]
    out = Assistant.keep_rules(top, top + rules, 4)
    assert [h.chunk_id for h in out] == ["w0", "r1", "w1", "r2"]


class Chat:
    def __init__(self, reply="", exc=None):
        self.reply, self.exc, self.calls = reply, exc, []

    def chat(self, system, user, model, max_tokens=700, keep_alive=None):
        self.calls.append(user)
        if self.exc:
            raise self.exc
        return self.reply


def test_rerank_orders_by_the_models_numbers_and_degrades_gracefully():
    a = bare()
    hits = [hit(str(i), f"Entry {i}", summary=f"s{i}") for i in range(5)]
    a.ollama = Chat("3, 1, 99, 3")
    out = a.rerank("q", hits, 3)
    assert [h.chunk_id for h in out] == ["2", "0", "1"]
    assert "1. Entry 0 (feat) — s0" in a.ollama.calls[0]
    a.ollama = Chat("")
    assert a.rerank("q", hits, 2) == hits[:2]
    a.ollama = Chat(exc=RuntimeError("boom"))
    assert a.rerank("q", hits, 2) == hits[:2]
    a.ollama = Chat(exc=OllamaError("down"))
    with pytest.raises(OllamaError):
        a.rerank("q", hits, 2)
    # Fewer candidates than k: no model call at all.
    a.ollama = Chat("1")
    assert a.rerank("q", hits[:2], 4) == hits[:2] and a.ollama.calls == []


def test_rerank_listing_marks_lore_and_levels():
    a = bare()
    a.ollama = Chat("1")
    hits = [hit("w", "Cheliax", corpus="pathfinderwiki", category="nation", text="Devils"),
            hit("g", "Gurglegut", category="creature", level=12, summary="Big")]
    a.rerank("q", hits, 1)
    assert "1. Cheliax (nation, lore) — Devils" in a.ollama.calls[0]
    assert "2. Gurglegut (creature) [level 12] — Big" in a.ollama.calls[0]


def test_rewrite_falls_back_to_an_empty_plan():
    a = bare()
    a.rewrite_system = None
    a.index = None
    a.ollama = Chat(exc=RuntimeError("no"))
    assert a.rewrite("q") == {"summary": "", "categories": [], "scope": "rules"}
    a.ollama = Chat("SUMMARY: s\nKINDS: feat")
    assert a.rewrite("q")["categories"] == ["feat"]
    a.ollama = Chat(exc=OllamaError("down"))
    with pytest.raises(OllamaError):
        a.rewrite("q")


def test_resolve_scope():
    a = bare()

    class WithLore:
        has_lore = True

    class WithoutLore:
        has_lore = False

    a.index = WithoutLore()
    assert a.resolve_scope("lore", {"scope": "lore"}) is False
    a.index = WithLore()
    assert a.resolve_scope("rules", {"scope": "lore"}) is False
    assert a.resolve_scope("lore", None) is True
    assert a.resolve_scope("auto", {"scope": "lore"}) is True
    assert a.resolve_scope("auto", {"scope": "rules"}) is False
    assert a.resolve_scope("auto", None) is False
    with pytest.raises(ValueError):
        a.resolve_scope("everything", None)


def test_condense_without_history_is_free():
    a = bare()
    a.ollama = Chat("anything")
    assert a.condense("q", []) == "q" and a.ollama.calls == []


OWLBEAR = ("# Owlbear\n\nA territorial predator with the body of a bear. " + "Flavour. " * 40 +
           "\n\n**Recall Knowledge - Animal** (Nature): DC 19\n\n## Owlbear (Creature 4)\n\n"
           "**Traits** N, Large, Animal\n\n**AC** 21\n\n**HP** 70\n\n**Melee** talon +14")


def test_stat_block_comes_first_for_creatures():
    h = hit("o", "Owlbear", category="creature", level=4, text=OWLBEAR)
    out = stat_block_first(h)
    assert out.startswith("## Owlbear (Creature 4)\n\n**Traits** N, Large, Animal")
    assert "**Melee** talon +14\n\nA territorial predator" in out
    assert "# Owlbear\n" not in out and "Recall Knowledge" in out
    # The excerpt at 1,600 characters now carries the numbers.
    a = bare(context_chars=200)
    assert "**AC** 21" in a.context([h])
    # Anything else is left exactly as it was.
    feat = hit("f", "Cat Fall", category="feat", text=OWLBEAR)
    assert stat_block_first(feat) == OWLBEAR
    plain = hit("p", "Plain", category="creature", text="## Plain (Creature 1)\n\n**AC** 1")
    assert stat_block_first(plain) == plain.text
    assert stat_block_first(hit("n", "No block", category="creature", text="just words")) == "just words"
