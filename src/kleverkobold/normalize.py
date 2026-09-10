"""Turn raw AoN documents into retrieval/training chunks.

AoN's ``markdown`` field is markdown plus a small pseudo-XML vocabulary
(``<title>``, ``<traits>``, ``<actions>``, ``<column>``, ``<table>`` ...).  We
render that down to plain markdown, and pull two things out on the way:

* **metadata** -- level, traits, rarity, source book, remaster status.  These
  become hard filters at retrieval time, which is what makes queries like
  "level 4 fighter feats with the flourish trait" work at all.
* **the outbound link graph** -- every entry links to the feats/spells/traits it
  depends on.  That graph is the natural seed for EntiGraph-style synthetic
  continued pretraining later, so we keep it rather than discarding the hrefs.
"""

from __future__ import annotations

import html
import re
from typing import Any

# --- AoN pseudo-XML ---------------------------------------------------------

RE_TITLE = re.compile(r"<title\b([^>]*)>(.*?)</title>", re.S)
RE_TRAITS = re.compile(r"<traits\b[^>]*>(.*?)</traits>", re.S)
RE_TRAIT = re.compile(r'<trait\b[^>]*label="([^"]*)"[^>]*/?>')
RE_ACTIONS = re.compile(r'<actions\b[^>]*string="([^"]*)"[^>]*/?>')
RE_ATTR = re.compile(r'(\w+)="([^"]*)"')
RE_LINK = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
RE_SELFCLOSING = re.compile(r"<(?:actions|image|date)\b[^>]*/?>")
# AoN embeds one entry inside another: a rules page lists its activities as
# ``<document level="2" id="action-2629" />`` and renders the child in place.
# The child's text is not in the parent's markdown, so stripping the tag leaves
# "These are most common exploration activities." followed by nothing.
RE_DOCUMENT = re.compile(r'<document\b[^>]*\bid="([^"]+)"[^>]*/?>')
RE_EMBED = re.compile(r"\{\{document:([^}]+)\}\}")
RE_BLOCK = re.compile(r"</?(?:column|row|document|aside|spoilers|center|span|details)\b[^>]*>")
RE_BR = re.compile(r"<br\s*/?>", re.I)
RE_LI = re.compile(r"<li\b[^>]*>(.*?)</li>", re.S)
RE_LIST = re.compile(r"</?(?:ul|ol)\b[^>]*>")
RE_CELL = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.S)
RE_ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S)
RE_TABLE_WRAP = re.compile(r"</?(?:table|thead|tbody|tfoot|summary)\b[^>]*>")
RE_ANY_TAG = re.compile(r"</?[a-zA-Z][\w-]*\b[^>]*>")
RE_BLANKS = re.compile(r"\n{3,}")
RE_NETHYS_NOTE = re.compile(r"^[ \t]*_?\*?Nethys Note:[^\n]*\n?", re.M | re.I)


def _render_title(match: re.Match[str]) -> str:
    attrs = dict(RE_ATTR.findall(match.group(1)))
    level = int(attrs.get("level", "2") or 2)
    # The heading is the entry's name, not a link to itself.
    body = RE_LINK.sub(lambda m: m.group(1), match.group(2)).strip()
    right = attrs.get("right", "").strip()
    heading = f"{'#' * min(level, 6)} {body}"
    return f"{heading} ({right})" if right else heading


def _render_row(match: re.Match[str]) -> str:
    cells = [c.strip() for c in RE_CELL.findall(match.group(1))]
    return " | ".join(cells) + "\n"


def _render_link(match: re.Match[str]) -> str:
    label, href = match.group(1), match.group(2).strip()
    if href.startswith("/"):
        return f"[{label}](https://2e.aonprd.com{href})"
    if href.startswith("http"):
        return f"[{label}]({href})"
    return label


def to_markdown(raw: str, keep_embeds: bool = False) -> str:
    """Render AoN pseudo-XML markdown down to plain markdown.

    With ``keep_embeds`` each embedded ``<document id=... />`` becomes a
    ``{{document:id}}`` placeholder for :func:`resolve_embeds` to fill once every
    entry has been read; otherwise the tag is dropped as before.
    """
    if not raw:
        return ""
    text = raw
    if keep_embeds:
        text = RE_DOCUMENT.sub(lambda m: f"\n{{{{document:{m.group(1)}}}}}\n", text)
    text = RE_TRAITS.sub(lambda m: "**Traits** " + ", ".join(RE_TRAIT.findall(m.group(1))), text)
    text = RE_ACTIONS.sub(lambda m: f"[{m.group(1)}]", text)
    text = RE_TITLE.sub(_render_title, text)
    text = RE_ROW.sub(_render_row, text)
    text = RE_TABLE_WRAP.sub("", text)
    text = RE_LI.sub(lambda m: f"- {m.group(1).strip()}\n", text)
    text = RE_LIST.sub("", text)
    text = RE_BR.sub("\n", text)
    text = RE_BLOCK.sub("", text)
    text = RE_SELFCLOSING.sub("", text)
    text = RE_ANY_TAG.sub("", text)
    # Keep the Archives' own links: "grabbed" underlined and pointing at Grapple
    # is how the site reads, and the runtime can open a linked entry in place.
    # Retrieval and the prompt strip them again (retrieval.plain) -- URLs are
    # noise to an embedder and cost the answering model tokens.
    text = RE_LINK.sub(_render_link, text)
    text = html.unescape(text)
    # "Nethys Note: No description has been provided for this creature." is site
    # housekeeping, and a small model reads it as "this creature does not exist".
    text = RE_NETHYS_NOTE.sub("", text)
    text = RE_BLANKS.sub("\n\n", text)
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def extract_links(raw: str) -> list[dict[str, str]]:
    """Outbound entity references, deduped, in document order."""
    seen: dict[str, dict[str, str]] = {}
    for label, href in RE_LINK.findall(raw or ""):
        label = label.strip()
        if not label or not href.startswith("/"):
            continue
        seen.setdefault(f"{label}|{href}", {"name": label, "url": href})
    return list(seen.values())


# --- document -> chunk ------------------------------------------------------

def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _first(value: Any) -> str | None:
    items = _as_list(value)
    return items[0] if items else None


def remaster_status(doc: dict) -> str:
    """``legacy`` entries were superseded by the Remaster; ``remaster`` replaced one."""
    if doc.get("remaster_id"):
        return "legacy"
    if doc.get("legacy_id"):
        return "remaster"
    return "unaffected"


def to_chunk(doc: dict) -> dict:
    raw_md = doc.get("markdown") or ""
    body = to_markdown(raw_md, keep_embeds=True) or to_markdown(doc.get("text") or "")
    url = doc.get("url") or ""
    return {
        "id": f"aon:{doc['category']}:{doc.get('id') or doc.get('_es_id')}",
        "corpus": "aon",
        "category": doc["category"],
        "name": doc.get("name"),
        "type": doc.get("type"),
        "level": doc.get("level"),
        "traits": _as_list(doc.get("trait")),
        "rarity": doc.get("rarity"),
        "pfs": doc.get("pfs"),
        "book": _first(doc.get("primary_source")) or _first(doc.get("source")),
        "release_date": doc.get("release_date"),
        "remaster_status": remaster_status(doc),
        "legacy_id": doc.get("legacy_id"),
        "remaster_id": doc.get("remaster_id"),
        "legacy_name": doc.get("legacy_name"),
        "hidden": bool(doc.get("exclude_from_search")),
        "url": f"https://2e.aonprd.com{url}" if url.startswith("/") else url,
        "summary": doc.get("summary"),
        "text": body,
        "links": extract_links(raw_md),
        "embeds": RE_DOCUMENT.findall(raw_md),
        "n_chars": len(body),
    }


def _one_line(text: str, limit: int = 240) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("; "))
    return (cut[:end + 1] if end > limit // 2 else cut.rstrip() + "…")


def resolve_embeds(chunk: dict, lookup: dict[str, dict]) -> dict:
    """Fill a chunk's ``{{document:id}}`` placeholders from the entries they name.

    Each becomes one ``**Name:** summary`` line, the same shape AoN uses for
    its own sidebar lists, so a page that says "these are the most common
    exploration activities" is followed by the nine activities. The child
    entries stay separate chunks for the detail; the parent just names them.
    Children not in ``lookup`` (hidden entries, or a dump that predates them)
    are dropped silently, which is what happened to all of them before.
    """
    if not chunk.get("embeds"):
        return chunk
    linked = {f"{l['name']}|{l['url']}" for l in chunk.get("links") or []}

    def render(match: re.Match[str]) -> str:
        child = lookup.get(match.group(1))
        if not child or not child.get("name"):
            return ""
        url = child.get("url") or ""
        if url and f"{child['name']}|{url}" not in linked:
            chunk["links"].append({"name": child["name"], "url": url})
            linked.add(f"{child['name']}|{url}")
        line = _one_line(child.get("summary") or "")
        return f"**{child['name']}:** {line}" if line else f"**{child['name']}**"

    text = RE_EMBED.sub(render, chunk["text"])
    chunk["text"] = RE_BLANKS.sub("\n\n", text).strip()
    chunk["n_chars"] = len(chunk["text"])
    return chunk


def embed_lookup_entry(doc: dict) -> dict:
    """The little a parent needs to name an embedded child, and a Remaster entry its old name."""
    url = doc.get("url") or ""
    return {"name": doc.get("name"), "summary": doc.get("summary"),
            "url": f"https://2e.aonprd.com{url}" if url.startswith("/") else url}


def fill_legacy_name(chunk: dict, lookup: dict[str, dict]) -> dict:
    """Give a Remaster entry the name its legacy counterpart had, if it changed.

    AoN carries ``legacy_name`` on some renamed entries and not others -- Force
    Barrage has ``legacy_id`` pointing at Magic Missile but no ``legacy_name``,
    so "was Magic Missile renamed?" could not find it. The legacy entry is in the
    same dump, so its name is one lookup away. Written into the text as well as
    the metadata: the answering model reads the text, and "**Formerly** Magic
    Missile" is the fact the question is asking for.
    """
    if chunk.get("remaster_status") != "remaster":
        return chunk
    old = chunk.get("legacy_name") or []
    old = [old] if isinstance(old, str) else [n for n in old if n]
    for lid in _as_list(chunk.get("legacy_id")):
        name = (lookup.get(lid) or {}).get("name")
        if name and name.lower() != (chunk.get("name") or "").lower() and name not in old:
            old.append(name)
    chunk["legacy_name"] = old
    if old and "**Formerly**" not in chunk["text"]:
        line = "**Formerly** " + ", ".join(old)
        text = chunk["text"]
        # Right after the Source line, where the eye goes for provenance; else
        # after the heading block.
        src = text.find("**Source**")
        cut = text.find("\n", src) if src >= 0 else text.find("\n\n")
        if cut < 0:
            cut = len(text)
        chunk["text"] = text[:cut] + "\n\n" + line + text[cut:]
        chunk["n_chars"] = len(chunk["text"])
    return chunk


# --- PathfinderWiki ---------------------------------------------------------

RE_REF = re.compile(r"<ref\b[^>]*?/>|<ref\b.*?</ref>", re.S | re.I)
RE_COMMENT = re.compile(r"<!--.*?-->", re.S)
RE_HTML = re.compile(r"</?[a-zA-Z][\w-]*\b[^>]*>")
RE_HEADING = re.compile(r"^(=+)\s*(.*?)\s*\1\s*$", re.M)
RE_WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
RE_EXTLINK = re.compile(r"\[(?:https?|//)\S+\s+([^\]]+)\]")
RE_BOLDITAL = re.compile(r"'{2,5}")
RE_LISTMARK = re.compile(r"^[*#:;]+\s*", re.M)
RE_FILE_PREFIX = re.compile(r"^(?:file|image|category)\s*:", re.I)
# Innermost ``[[...]]`` only -- one containing no further link delimiters.
RE_INNER_LINK = re.compile(r"\[\[((?:(?!\[\[|\]\]).)*)\]\]", re.S)
# Wikitables and magic words are layout, not lore.
RE_WIKITABLE = re.compile(r"^[ \t]*\{\|.*?^[ \t]*\|\}", re.S | re.M)
RE_MAGIC = re.compile(r"__[A-Z]+__")
RE_MD_HEADING = re.compile(r"^(#{2,6}) (.*)$", re.M)

# Sections that are bibliography, not lore.
DROP_SECTIONS = {"references", "external links", "see also", "sources", "notes", "further reading",
                 "gallery"}

# Infobox parameters that carry pictures, citations and layout rather than facts.
INFOBOX_SKIP = {"image", "caption", "imagesize", "image size", "alt", "name", "title", "titles",
                "imagecaption", "map", "symbol", "type", "spoiled", "adjective"}
RE_SKIP_KEY = re.compile(r"source|page|spoil|image|map$|^ref|latlong|^lat$|^long$|coord", re.I)
# Templates that open a page but are not its infobox: spoiler badges, map
# embeds, timeline boxes, hatnotes, maintenance. The infobox is the first
# template that is none of these and has named parameters.
NON_INFOBOX = {"badges", "displaymap", "yearbox", "update", "ref", "legacy-content", "quote",
               "characters", "spoiled", "stub", "cleanup", "main", "see-also", "for", "about",
               "redirect", "dablink", "hatnote", "disambig", "disambiguation", "toc", "clear",
               "reflist", "wip", "expand", "merge", "delete", "nsfw", "canon", "noncanon",
               "non-canon", "pathfinderwiki", "infobox-start", "infobox-end", "date", "ordinal",
               "pronounce", "abbr", "plain", "ill", "lang", "n", "clr", "tabber", "tab", "note",
               "featured", "good", "sidebar", "navbox", "quotebox", "sic", "adventure-overview-start"}
# Template names that mean the same page kind as a plainer one.
CATEGORY_ALIAS = {"creature-tabbed": "creature", "biography": "person",
                  "adventure-overview": "adventure", "magic-item": "item",
                  "alchemical-item": "item", "location-tabbed": "location"}
RE_EMPTY_PARENS = re.compile(r"\s*\((?:aged?)?\s*\)")   # "4692 AR (age )": a template with no year to count from
RE_HATNOTE = re.compile(r"^(?:- )?(?:This (?:article|page) (?:is|covers|describes|deals|refers)|"
                        r"For (?:the|other|a|an) |See also |Not to be confused|"
                        r"\"?[A-Z][\w' ]+\"? redirects here)", re.I)


def _strip_templates(text: str) -> str:
    """Remove ``{{...}}`` including nested braces, which mwparserfromhell keeps as nodes."""
    out, depth, i = [], 0, 0
    while i < len(text):
        if text.startswith("{{", i):
            depth += 1
            i += 2
        elif text.startswith("}}", i) and depth:
            depth -= 1
            i += 2
        else:
            if not depth:
                out.append(text[i])
            i += 1
    return "".join(out)


def wiki_infobox(wikitext: str) -> dict[str, str]:
    """First template's named parameters -- the structured lore on a page."""
    try:
        import mwparserfromhell
    except ImportError:  # pragma: no cover
        return {}
    code = mwparserfromhell.parse(wikitext)
    for template in code.filter_templates(recursive=False):
        name = re.sub(r"[\s_]+", "-", str(template.name).strip().lower())
        if name in NON_INFOBOX or name.startswith(("cite", "sic", "quote")):
            continue
        fields = {}
        for param in template.params:
            if not param.showkey:
                continue
            key = str(param.name).strip()
            value = str(param.value).strip()
            value = RE_COMMENT.sub("", value)
            value = RE_REF.sub("", value)
            value = re.sub(r"<br\s*/?>", ", ", value, flags=re.I)
            value = _strip_templates(_resolve_wikilinks(value))
            value = RE_HTML.sub("", value)
            value = RE_BOLDITAL.sub("", value)
            value = RE_EMPTY_PARENS.sub("", html.unescape(value)).strip(" ,;")
            if key and value:
                fields[key] = value
        if fields:
            return {"_template": str(template.name).strip(), **fields}
    return {}


def _resolve_wikilinks(text: str) -> str:
    """Flatten ``[[...]]`` links, innermost first, dropping File:/Image:/Category: ones.

    Image captions nest links (``[[File:x.jpg|thumb|An [[Asmodeus|Asmodean]] cathedral]]``).
    A single non-nested regex pass matches the *outer* brackets against the *inner*
    closer and leaves ``cathedral]]`` debris behind, so we resolve innermost-out
    until the text stops changing.  The display text is the last pipe-separated
    field, which is correct for both ``[[Page]]`` and ``[[Page|label]]``.
    """

    def render(match: re.Match[str]) -> str:
        body = match.group(1)
        if RE_FILE_PREFIX.match(body.strip()):
            return ""
        return body.rsplit("|", 1)[-1].strip()

    for _ in range(8):
        replaced = RE_INNER_LINK.sub(render, text)
        if replaced == text:
            return text
        text = replaced
    return text


def wiki_prose(wikitext: str) -> str:
    """Wikitext down to readable prose, keeping section headings."""
    text = RE_COMMENT.sub("", wikitext)
    text = RE_REF.sub("", text)
    text = RE_WIKITABLE.sub("", text)
    text = _strip_templates(text)
    text = _resolve_wikilinks(text)
    text = RE_EXTLINK.sub(lambda m: m.group(1), text)
    text = RE_HTML.sub("", text)
    text = RE_MAGIC.sub("", text)
    text = RE_BOLDITAL.sub("", text)
    text = RE_LISTMARK.sub("- ", text)

    kept, skipping = [], False
    for line in text.splitlines():
        heading = RE_HEADING.match(line.strip())
        if heading:
            title = heading.group(2).strip()
            skipping = title.lower() in DROP_SECTIONS
            if not skipping:
                kept.append(f"{'#' * len(heading.group(1))} {title}")
            continue
        if not skipping:
            kept.append(line.rstrip())
    text = html.unescape("\n".join(kept))
    return RE_BLANKS.sub("\n\n", text).strip()


def wiki_category(infobox: dict) -> str:
    """The page's kind, from its infobox template: person, city, nation, deity..."""
    name = re.sub(r"[\s_]+", "-", (infobox.get("_template") or "article").strip().lower())
    return CATEGORY_ALIAS.get(name, name)


def wiki_facts(infobox: dict) -> str:
    """The infobox as ``**Field** value`` lines, the shape an AoN stat block uses.

    A nation's capital, a deity's domains, a person's homeland are the facts a
    lore question asks for first, and they sit in the infobox rather than the
    prose. Written as bold-labelled lines they read the same way the runtime's
    stat-block renderer reads ``**Traits**`` and ``**Source**``, so they need no
    UI work, and the answering model gets "**Ruler** Abrogail Thrune II" instead
    of having to find it in a paragraph.
    """
    lines = []
    for key, value in infobox.items():
        k = key.lower().strip()
        if k.startswith("_") or k in INFOBOX_SKIP or RE_SKIP_KEY.search(k):
            continue
        value = " ".join(value.split())
        if not value or len(value) > 200 or value.lower() in ("none", "unknown", "n/a", "-"):
            continue
        label = key.replace("_", " ").strip()
        label = label[0].upper() + label[1:]
        lines.append(f"**{label}** {value}")
    return "\n".join(lines)


def _sentence(text: str, limit: int = 240) -> str:
    """The first sentence of a passage, for the summary index."""
    text = " ".join((text or "").split())
    m = re.match(r"(.+?[.!?])(?:\s|$)", text)
    first = m.group(1) if m and len(m.group(1)) >= 40 else text
    return _one_line(first, limit)


def _first_paragraph(prose: str) -> str:
    """The first real paragraph: not a heading, a fact line, a rule, or a hatnote."""
    for block in prose.split("\n\n"):
        block = block.strip()
        if (not block or block.startswith(("#", "**")) or set(block) <= set("-= ")
                or RE_HATNOTE.match(block)):
            continue
        return block
    return ""


def _drop_hatnotes(prose: str) -> str:
    """Remove the "This article is about X. For Y, see Z." lines that open a page."""
    blocks = prose.split("\n\n")
    while blocks and (RE_HATNOTE.match(blocks[0].strip()) or set(blocks[0].strip()) <= set("-= ")):
        blocks.pop(0)
    return "\n\n".join(blocks)


def wiki_to_chunk(page: dict) -> dict:
    prose = _drop_hatnotes(wiki_prose(page["wikitext"]))
    infobox = wiki_infobox(page["wikitext"])
    title = page["title"]
    return {
        "id": f"wiki:{page['pageid']}",
        "corpus": "pathfinderwiki",
        "category": wiki_category(infobox),
        "name": title,
        "url": "https://pathfinderwiki.com/wiki/" + title.replace(" ", "_"),
        "revid": page.get("revid"),
        "timestamp": page.get("timestamp"),
        "infobox": infobox,
        "summary": _sentence(_first_paragraph(prose)),
        "text": prose,
        "n_chars": len(prose),
        "license": "Paizo Community Use Policy",
    }


def _anchor(title: str) -> str:
    """MediaWiki's section anchor: spaces to underscores, the rest percent-encoded."""
    from urllib.parse import quote
    return quote(title.replace(" ", "_"), safe="_-.:()'")


def _split_long(body: str, limit: int) -> list[str]:
    """Cut a section at paragraph boundaries so no piece exceeds ``limit``."""
    pieces, current = [], ""
    for para in body.split("\n\n"):
        if current and len(current) + len(para) + 2 > limit:
            pieces.append(current.strip())
            current = ""
        current += para + "\n\n"
    if current.strip():
        pieces.append(current.strip())
    return pieces or [body]


def wiki_to_chunks(page: dict, split_at: int = 2500, min_section: int = 300,
                   max_section: int = 6000) -> list[dict]:
    """A page as retrieval chunks: the lead with its infobox, then one per section.

    AoN entries are atomic, so one chunk each is right. A wiki page is not:
    Cheliax runs to tens of thousands of characters, and "who rules Cheliax?"
    is answered in its Government section, which neither the embedder (which
    reads the first 1,200 characters) nor the answering model (1,600) would ever
    see. Short pages stay whole; long ones split at their headings, small
    sections merged into the one before, and each carries the page name so
    "Cheliax › History" still says what it is about. The lead chunk keeps the
    page's id and URL, so the whole page is one click away from any of them.
    """
    base = wiki_to_chunk(page)
    prose = base["text"]
    facts = wiki_facts(base["infobox"])

    def with_facts(text: str) -> str:
        return (facts + "\n\n" + text).strip() if facts else text

    if len(prose) <= split_at:
        base["text"] = with_facts(prose)
        base["n_chars"] = len(base["text"])
        base["section"] = ""
        return [base]

    # Split at level-2 and level-3 headings, remembering the level-2 parent.
    parts: list[tuple[list[str], str]] = []  # (heading path, body)
    path: list[str] = []
    pos = 0
    for m in RE_MD_HEADING.finditer(prose):
        body = prose[pos:m.start()].strip()
        if not parts:
            parts.append(([], body))          # the lead, possibly empty
        else:
            parts.append((list(path), body))
        level, title = len(m.group(1)), m.group(2).strip()
        path = [title] if level <= 2 else (path[:1] + [title])
        pos = m.end()
    parts.append((list(path) if parts else [], prose[pos:].strip()))

    # Merge sections too small to stand alone into the one before them.
    merged: list[tuple[list[str], str]] = []
    for heads, body in parts:
        if merged and len(body) < min_section and merged[-1][0] and heads:
            prev_heads, prev_body = merged[-1]
            merged[-1] = (prev_heads, prev_body + "\n\n## " + " › ".join(heads[len(prev_heads):] or heads) + "\n\n" + body)
        else:
            merged.append((heads, body))

    chunks: list[dict] = []
    for heads, body in merged:
        if not heads:
            lead = dict(base)
            lead["text"] = with_facts(body) if body else with_facts("")
            lead["section"] = ""
            lead["n_chars"] = len(lead["text"])
            if lead["n_chars"]:
                chunks.append(lead)
            continue
        for n, piece in enumerate(_split_long(body, max_section)):
            if len(piece) < 80:
                continue
            chunk = {k: v for k, v in base.items() if k != "infobox"}
            section = " › ".join(heads)
            chunk["id"] = f"{base['id']}#{_anchor(heads[-1])}" + (f"-{n + 1}" if n else "")
            chunk["name"] = f"{base['name']} › {section}" + (f" ({n + 1})" if n else "")
            chunk["section"] = section
            chunk["url"] = base["url"] + "#" + _anchor(heads[-1])
            chunk["summary"] = _sentence(_first_paragraph(piece)) or _sentence(piece)
            chunk["text"] = f"## {section}\n\n{piece}"
            chunk["n_chars"] = len(chunk["text"])
            chunks.append(chunk)
    return chunks or [base]
