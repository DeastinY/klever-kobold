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


def _render_title(match: re.Match[str]) -> str:
    attrs = dict(RE_ATTR.findall(match.group(1)))
    level = int(attrs.get("level", "2") or 2)
    body = match.group(2).strip()
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
    """The little a parent needs to name an embedded child."""
    url = doc.get("url") or ""
    return {"name": doc.get("name"), "summary": doc.get("summary"),
            "url": f"https://2e.aonprd.com{url}" if url.startswith("/") else url}


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

# Sections that are bibliography, not lore.
DROP_SECTIONS = {"references", "external links", "see also", "sources", "notes", "further reading"}


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
        fields = {}
        for param in template.params:
            if not param.showkey:
                continue
            key = str(param.name).strip()
            value = str(param.value).strip()
            value = RE_COMMENT.sub("", value)
            value = _strip_templates(_resolve_wikilinks(value)).strip()
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
    text = _strip_templates(text)
    text = _resolve_wikilinks(text)
    text = RE_EXTLINK.sub(lambda m: m.group(1), text)
    text = RE_HTML.sub("", text)
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


def wiki_to_chunk(page: dict) -> dict:
    prose = wiki_prose(page["wikitext"])
    infobox = wiki_infobox(page["wikitext"])
    title = page["title"]
    return {
        "id": f"wiki:{page['pageid']}",
        "corpus": "pathfinderwiki",
        "category": infobox.get("_template", "article").lower(),
        "name": title,
        "url": "https://pathfinderwiki.com/wiki/" + title.replace(" ", "_"),
        "revid": page.get("revid"),
        "timestamp": page.get("timestamp"),
        "infobox": infobox,
        "text": prose,
        "n_chars": len(prose),
        "license": "Paizo Community Use Policy",
    }
