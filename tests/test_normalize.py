"""AoN pseudo-XML and PathfinderWiki wikitext down to the chunks the index holds."""

import pytest

from kleverkobold import normalize as n


# --- AoN markdown -------------------------------------------------------------

def test_title_becomes_heading_with_right_hand_label():
    raw = '<title level="1" right="Feat 4">[Cat Fall](/Feats.aspx?ID=1)</title>'
    assert n.to_markdown(raw) == "# Cat Fall (Feat 4)"


def test_title_level_is_capped_at_six_and_defaults_to_two():
    assert n.to_markdown("<title>Plain</title>") == "## Plain"
    assert n.to_markdown('<title level="9">Deep</title>') == "###### Deep"


def test_traits_actions_and_tables_render():
    raw = ('<traits><trait label="Fire" /><trait label="Manipulate"/></traits>\n'
           '<actions string="Single Action" /> Strike\n'
           "<table><tr><td>Level</td><td>1</td></tr><tr><td>Level</td><td>2</td></tr></table>")
    out = n.to_markdown(raw)
    assert "**Traits** Fire, Manipulate" in out
    assert "[Single Action] Strike" in out
    assert "Level | 1\nLevel | 2" in out


def test_lists_breaks_and_unknown_tags():
    raw = "<ul><li>one</li><li> two </li></ul>a<br/>b<column>c</column><weird attr=1>d</weird>"
    out = n.to_markdown(raw)
    assert out.startswith("- one\n- two")
    assert "a\nb" in out
    assert "cd" in out and "<" not in out


def test_links_are_absolute_or_dropped():
    raw = "[Grapple](/Actions.aspx?ID=1) [Site](https://x.y/z) [nowhere](Sources.aspx)"
    out = n.to_markdown(raw)
    assert "[Grapple](https://2e.aonprd.com/Actions.aspx?ID=1)" in out
    assert "[Site](https://x.y/z)" in out
    assert out.endswith("nowhere")


def test_nethys_note_and_entities_and_blank_runs():
    raw = "A &amp; B\n\n\n\n*Nethys Note: No description has been provided.*\nC  "
    assert n.to_markdown(raw) == "A & B\n\nC"


def test_empty_input():
    assert n.to_markdown("") == ""
    assert n.to_markdown(None) == ""


def test_keep_embeds_leaves_a_placeholder():
    raw = 'Before <document level="2" id="action-1" /> after'
    assert "{{document:action-1}}" in n.to_markdown(raw, keep_embeds=True)
    assert "document" not in n.to_markdown(raw)


def test_extract_links_dedupes_and_keeps_order():
    raw = "[A](/a) [B](/b) [A](/a) [](/empty) [Ext](https://e)"
    assert n.extract_links(raw) == [{"name": "A", "url": "/a"}, {"name": "B", "url": "/b"}]
    assert n.extract_links(None) == []


@pytest.mark.parametrize("doc, want", [
    ({"remaster_id": "x"}, "legacy"),
    ({"legacy_id": ["y"]}, "remaster"),
    ({}, "unaffected"),
    ({"remaster_id": None, "legacy_id": None}, "unaffected"),
])
def test_remaster_status(doc, want):
    assert n.remaster_status(doc) == want


def test_to_chunk_shapes_a_document():
    doc = {"category": "feat", "id": "feat-7", "name": "Cat Fall", "type": "Feat", "level": 1,
           "trait": "General", "rarity": "common", "primary_source": ["Player Core"],
           "url": "/Feats.aspx?ID=7", "summary": "Fall less.",
           "markdown": '<title right="Feat 1">Cat Fall</title>[Acrobatics](/Skills.aspx?ID=1)'
                       ' <document id="action-9" />',
           "exclude_from_search": True, "legacy_id": "feat-3"}
    chunk = n.to_chunk(doc)
    assert chunk["id"] == "aon:feat:feat-7"
    assert chunk["corpus"] == "aon"
    assert chunk["traits"] == ["General"]
    assert chunk["book"] == "Player Core"
    assert chunk["url"] == "https://2e.aonprd.com/Feats.aspx?ID=7"
    assert chunk["remaster_status"] == "remaster"
    assert chunk["hidden"] is True
    assert chunk["links"] == [{"name": "Acrobatics", "url": "/Skills.aspx?ID=1"}]
    assert chunk["embeds"] == ["action-9"]
    assert chunk["n_chars"] == len(chunk["text"])
    assert "{{document:action-9}}" in chunk["text"]


def test_to_chunk_falls_back_to_text_and_es_id():
    doc = {"category": "rules", "_es_id": "rules-1", "text": "plain words", "source": "GM Core"}
    chunk = n.to_chunk(doc)
    assert chunk["id"] == "aon:rules:rules-1"
    assert chunk["text"] == "plain words"
    assert chunk["book"] == "GM Core"
    assert chunk["url"] == ""


def test_resolve_embeds_fills_children_and_adds_links():
    chunk = {"text": "Activities:\n\n{{document:a1}}\n{{document:a2}}\n{{document:missing}}",
             "embeds": ["a1", "a2", "missing"], "links": []}
    lookup = {"a1": {"name": "Search", "summary": "Look around. Carefully.",
                     "url": "https://2e.aonprd.com/Actions.aspx?ID=1"},
              "a2": {"name": "Hustle", "summary": "", "url": ""}}
    out = n.resolve_embeds(chunk, lookup)
    assert "**Search:** Look around. Carefully." in out["text"]
    assert "**Hustle**" in out["text"]
    assert "missing" not in out["text"]
    assert out["links"] == [{"name": "Search", "url": "https://2e.aonprd.com/Actions.aspx?ID=1"}]
    assert out["n_chars"] == len(out["text"])


def test_resolve_embeds_without_embeds_is_identity():
    chunk = {"text": "x", "embeds": []}
    assert n.resolve_embeds(chunk, {}) is chunk


def test_one_line_cuts_at_a_sentence():
    long = "First sentence is here. " * 20
    out = n._one_line(long, limit=100)
    assert out.endswith(".") and len(out) <= 100
    assert n._one_line("x" * 300, limit=100).endswith("…")
    assert n._one_line("  a   b  ") == "a b"


def test_fill_legacy_name_writes_formerly_after_source():
    chunk = {"remaster_status": "remaster", "legacy_id": "180", "name": "Force Barrage",
             "text": "# Force Barrage\n\n**Source** Player Core pg. 1\n\nYou fire.",
             "legacy_name": None}
    out = n.fill_legacy_name(chunk, {"180": {"name": "Magic Missile"}})
    assert out["legacy_name"] == ["Magic Missile"]
    assert "**Source** Player Core pg. 1\n\n**Formerly** Magic Missile\n\nYou fire." in out["text"]
    # Idempotent: a second pass neither duplicates the name nor the line.
    again = n.fill_legacy_name(dict(out), {"180": {"name": "Magic Missile"}})
    assert again["text"].count("**Formerly**") == 1


def test_fill_legacy_name_skips_same_name_and_non_remaster():
    same = {"remaster_status": "remaster", "legacy_id": "1", "name": "Shield", "text": "t"}
    assert n.fill_legacy_name(same, {"1": {"name": "shield"}})["legacy_name"] == []
    legacy = {"remaster_status": "legacy", "text": "t"}
    assert n.fill_legacy_name(legacy, {}) is legacy


def test_embed_lookup_entry():
    assert n.embed_lookup_entry({"name": "A", "summary": "s", "url": "/x"}) == {
        "name": "A", "summary": "s", "url": "https://2e.aonprd.com/x"}


# --- wikitext -----------------------------------------------------------------

def test_strip_templates_handles_nesting():
    assert n._strip_templates("a {{b {{c}} d}} e") == "a  e"
    assert n._strip_templates("unbalanced }} stays") == "unbalanced }} stays"


def test_resolve_wikilinks_innermost_first():
    text = "[[File:x.jpg|thumb|An [[Asmodeus|Asmodean]] cathedral]] in [[Cheliax]]"
    assert n._resolve_wikilinks(text) == " in Cheliax"
    assert n._resolve_wikilinks("[[Page|label]]") == "label"
    assert n._resolve_wikilinks("[[Category:Nations]]") == ""


def test_wiki_prose_drops_bibliography_sections_and_markup():
    wikitext = ("{{Nation|capital=Egorian}}\n'''Cheliax''' is a nation.<ref>cite</ref>\n"
                "<!-- hidden -->\n== History ==\n* first\n* second\n"
                "{| class=\"wikitable\"\n| cell\n|}\n__NOTOC__ [http://x.y label]\n"
                "== References ==\n<references/>\n== See also ==\n* [[Other]]")
    out = n.wiki_prose(wikitext)
    assert out.startswith("Cheliax is a nation.")
    assert "## History\n- first\n- second" in out
    assert "cite" not in out and "hidden" not in out and "cell" not in out
    assert "References" not in out and "Other" not in out
    assert "label" in out and "NOTOC" not in out


def test_wiki_infobox_and_facts():
    mw = pytest.importorskip("mwparserfromhell")
    assert mw
    wikitext = ("{{Badges|canon}}\n{{Nation\n| image = x.jpg\n| capital = [[Egorian]]\n"
                "| ruler = [[Abrogail Thrune II]]<ref>x</ref>\n| source = Book\n"
                "| founded = 4081 AR (age )\n| religion = none\n}}\nProse.")
    box = n.wiki_infobox(wikitext)
    assert box["_template"] == "Nation"
    assert box["capital"] == "Egorian"
    assert box["ruler"] == "Abrogail Thrune II"
    assert box["founded"] == "4081 AR"
    assert box["image"] == "x.jpg"          # kept on the box, dropped from the facts
    facts = n.wiki_facts(box)
    assert "Image" not in facts
    assert "**Capital** Egorian" in facts
    assert "**Ruler** Abrogail Thrune II" in facts
    assert "Source" not in facts and "religion" not in facts.lower()
    assert n.wiki_category(box) == "nation"


def test_wiki_infobox_empty_when_only_layout_templates():
    pytest.importorskip("mwparserfromhell")
    assert n.wiki_infobox("{{Badges|canon}} {{stub}} text") == {}


def test_wiki_category_aliases():
    assert n.wiki_category({"_template": "Creature tabbed"}) == "creature"
    assert n.wiki_category({"_template": "Magic_item"}) == "item"
    assert n.wiki_category({}) == "article"


def test_wiki_facts_skips_long_values_and_underscores():
    box = {"_template": "Person", "home_land": "Absalom", "bio": "x" * 201, "died": "-"}
    assert n.wiki_facts(box) == "**Home land** Absalom"


def test_sentence_and_first_paragraph_and_hatnotes():
    prose = ("This article is about the nation. For the city, see Egorian.\n\n"
             "**Capital** Egorian\n\n----\n\nCheliax is a devil-bound nation with a long "
             "and troubled history. It fell to Thrune.\n\nMore.")
    assert n._first_paragraph(prose).startswith("Cheliax is a devil-bound")
    assert n._sentence(n._first_paragraph(prose)) == (
        "Cheliax is a devil-bound nation with a long and troubled history.")
    assert n._sentence("Short. Then more words follow here.") == "Short. Then more words follow here."
    assert n._drop_hatnotes(prose).startswith("**Capital**")
    assert n._first_paragraph("") == ""


def test_anchor_and_split_long():
    assert n._anchor("Government & law") == "Government_%26_law"
    body = "\n\n".join(["p" * 40] * 5)
    pieces = n._split_long(body, limit=100)
    assert all(len(p) <= 100 for p in pieces) and len(pieces) == 3
    assert n._split_long("", 10) == [""]


def _page(text: str, title="Cheliax", pageid=100):
    return {"pageid": pageid, "title": title, "wikitext": text, "revid": 7,
            "timestamp": "2026-01-01T00:00:00Z"}


def test_wiki_to_chunk_basic_shape():
    chunk = n.wiki_to_chunk(_page("'''Cheliax''' is a nation of devils and lawyers."))
    assert chunk["id"] == "wiki:100"
    assert chunk["corpus"] == "pathfinderwiki"
    assert chunk["url"] == "https://pathfinderwiki.com/wiki/Cheliax"
    assert chunk["summary"] == "Cheliax is a nation of devils and lawyers."
    assert chunk["license"].startswith("Paizo")


def test_wiki_to_chunks_short_page_stays_whole():
    chunks = n.wiki_to_chunks(_page("Short lead.\n\n== History ==\nBrief."))
    assert len(chunks) == 1 and chunks[0]["section"] == ""


def test_wiki_to_chunks_splits_long_pages_at_headings():
    lead = "Cheliax is a nation. " * 10
    history = "Long ago things happened here in detail. " * 30
    government = "The queen rules with infernal contracts. " * 30
    tiny = "A footnote."
    page = _page(f"{lead}\n\n== History ==\n{history}\n\n=== Early ===\n{tiny}\n\n"
                 f"== Government ==\n{government}")
    chunks = n.wiki_to_chunks(page, split_at=200, min_section=50)
    names = [c["name"] for c in chunks]
    assert names[0] == "Cheliax"
    assert "Cheliax › History" in names and "Cheliax › Government" in names
    assert not any("Early" in name for name in names)   # merged into History
    gov = next(c for c in chunks if c["section"] == "Government")
    assert gov["id"] == "wiki:100#Government"
    assert gov["url"].endswith("#Government")
    assert gov["text"].startswith("## Government\n\n")
    assert "infobox" not in gov
    history_chunk = next(c for c in chunks if c["section"] == "History")
    assert "## Early" in history_chunk["text"]


def test_wiki_to_chunks_numbers_oversized_sections():
    body = "\n\n".join(["Paragraph of lore. " * 20] * 6)
    page = _page(f"Lead.\n\n== Saga ==\n{body}")
    chunks = n.wiki_to_chunks(page, split_at=100, max_section=900)
    sagas = [c for c in chunks if c["section"] == "Saga"]
    assert len(sagas) >= 2
    assert sagas[1]["id"].endswith("-2") and sagas[1]["name"].endswith("(2)")
