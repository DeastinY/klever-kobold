"""A kobold-sized index and a model that never leaves the process.

Every test that needs an ``Assistant`` gets one built over a real index
directory -- manifest, metadata, bodies, both embedding matrices, the BM25
arrays, the link graph -- written by :func:`build_index` from a dozen made-up
entries. The embedder is a hashed bag of words, so a query that shares words
with an entry lands near it, which is all retrieval needs to be exercised end
to end. The language model replies with whatever the test queued.
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

import numpy as np
import orjson
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from kleverkobold import retrieval
from kleverkobold.app import Assistant
from kleverkobold.bm25 import BM25

DIM = 64
QUERY_PREFIX = "Query: "
PROBE_TEXT = "Treat falls as shorter than they are."


def embed_text(text: str) -> np.ndarray:
    """A deterministic unit vector: each token adds one hashed basis direction."""
    vec = np.zeros(DIM, dtype=np.float32)
    for token in retrieval.tokenize(text):
        digest = hashlib.md5(token.encode()).digest()
        vec[digest[0] % DIM] += 1.0
        vec[digest[1] % DIM] += 0.5
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm else vec


def _aon(cid: str, name: str, category: str, text: str, summary: str, level=None,
         traits=(), status="unaffected", book="Player Core", **extra) -> dict:
    row = {"id": f"aon:{category}:{cid}", "corpus": "aon", "name": name, "category": category,
           "level": level, "traits": list(traits), "rarity": "common", "book": book,
           "remaster_status": status, "remaster_id": None, "legacy_id": None,
           "legacy_name": [], "url": f"https://2e.aonprd.com/{category.title()}.aspx?ID={cid}",
           "summary": summary, "text": text}
    row.update(extra)
    return row


def _wiki(pageid: str, name: str, category: str, text: str, summary: str,
          section: str = "") -> dict:
    anchor = "#" + section.replace(" ", "_") if section else ""
    return {"id": f"wiki:{pageid}{anchor}", "corpus": "pathfinderwiki",
            "name": name if not section else f"{name} › {section}", "category": category,
            "level": None, "traits": [], "rarity": None, "book": None,
            "remaster_status": "unaffected", "remaster_id": None, "legacy_id": None,
            "legacy_name": [], "section": section,
            "url": f"https://pathfinderwiki.com/wiki/{name.replace(' ', '_')}{anchor}",
            "summary": summary, "text": text}


ENTRIES = [
    _aon("2399", "Treat Wounds", "action",
         "# Treat Wounds (Action)\n\n**Traits** Exploration, Healing, Manipulate\n\n"
         "**Source** [Player Core](https://2e.aonprd.com/Sources.aspx?ID=1) pg. 249\n\n"
         "You spend 10 minutes treating one injured living creature. Attempt a "
         "[Medicine](https://2e.aonprd.com/Skills.aspx?ID=42) check against DC 15. "
         "On a success the target regains 2d8 Hit Points.",
         "Restore Hit Points to a living creature over ten minutes.",
         traits=("Exploration", "Healing", "Manipulate")),
    _aon("42", "Medicine", "skill",
         "# Medicine\n\nYou can patch up wounds and help people recover from diseases. "
         "Nethys Note: No description has been provided.\n\nTreat Wounds is trained only.",
         "Patch up wounds and diagnose diseases."),
    _aon("2001", "Battle Medicine", "feat",
         "# Battle Medicine (Feat 1)\n\n**Traits** General, Healing, Manipulate, Skill\n\n"
         "You can patch up wounds, even in combat. Attempt a Medicine check with the same "
         "DC as Treat Wounds.",
         "Patch up wounds in the middle of combat, once per day per target.",
         level=1, traits=("General", "Healing", "Manipulate", "Skill")),
    _aon("180", "Magic Missile", "spell",
         "# Magic Missile (Spell 1)\n\nYou fire a shard of magical force.",
         "Legacy: fire darts of force.", level=1, status="legacy",
         remaster_id=["1585"], book="Core Rulebook"),
    _aon("1585", "Force Barrage", "spell",
         "# Force Barrage (Spell 1)\n\n**Formerly** Magic Missile\n\nYou fire a shard of force "
         "that unerringly strikes one creature.",
         "Fire darts of pure force that always hit.", level=1, status="remaster",
         legacy_id="180", legacy_name=["Magic Missile"]),
    _aon("37", "Prone", "condition",
         "# Prone\n\nYou're lying on the ground. You are off-guard and take a -2 "
         "circumstance penalty to attack rolls. Standing up takes the Stand action.",
         "Lying on the ground: off-guard, and a penalty to attacks."),
    _aon("1200", "Gurglegut", "creature",
         "# Gurglegut (Creature 12)\n\nA bloated swamp dragon that swallows boats whole.",
         "A bloated swamp dragon, level 12.", level=12, traits=("Dragon", "Water")),
    _aon("2399b", "Treat Wounds", "action",
         "# Treat Wounds (Action)\n\nThe older printing of the same activity: 10 minutes, "
         "Medicine check, DC 15.",
         "Restore Hit Points over ten minutes (older printing).", book="Core Rulebook",
         traits=("Exploration", "Healing", "Manipulate")),
    _aon("9", "Desna", "deity",
         "# Desna\n\n**Domains** dreams, luck, stars, travel\n\n**Favored Weapon** starknife\n\n"
         "Desna is the Song of the Spheres.",
         "Goddess of dreams, luck, stars and travelers; favored weapon starknife."),
    _wiki("100", "Cheliax", "nation",
          "**Capital** Egorian\n**Ruler** Abrogail Thrune II\n\nCheliax is a devil-bound "
          "nation on the Inner Sea, ruled by House Thrune since the civil war.",
          "Cheliax is a devil-bound nation on the Inner Sea ruled by House Thrune."),
    _wiki("100", "Cheliax", "nation",
          "## Government\n\nThe nation is ruled by Queen Abrogail Thrune II from the "
          "capital Egorian, with infernal contracts binding the nobility.",
          "The nation is ruled by Queen Abrogail Thrune II from Egorian.",
          section="Government"),
    _wiki("101", "Desna", "deity",
          "Desna is the goddess of dreams, luck, stars and travelers, one of the oldest "
          "deities of Golarion. Her followers wander the roads under the night sky.",
          "Desna is the goddess of dreams, luck, stars and travelers."),
]

LINKS = [
    {"id": "aon:skill:medicine", "to": ["aon:action:2399", "aon:feat:2001"]},
    {"id": "aon:action:2399", "to": ["aon:skill:42"]},
    {"id": "aon:feat:2001", "to": ["aon:action:2399", "aon:skill:42"]},
]


def build_index(directory: pathlib.Path, entries: list[dict] = ENTRIES) -> pathlib.Path:
    """Write every file ``Assistant`` reads, the way scripts/package_index.py does."""
    directory.mkdir(parents=True, exist_ok=True)
    meta_rows, body_rows = [], []
    for row in entries:
        body_rows.append({"id": row["id"], "text": row["text"]})
        meta = {k: v for k, v in row.items() if k != "text"}
        meta["n_chars"] = len(row["text"])
        meta_rows.append(meta)
    (directory / "meta.jsonl").write_bytes(b"".join(orjson.dumps(m) + b"\n" for m in meta_rows))
    (directory / "bodies.jsonl").write_bytes(b"".join(orjson.dumps(b) + b"\n" for b in body_rows))
    (directory / "links.jsonl").write_bytes(b"".join(orjson.dumps(line) + b"\n" for line in LINKS))
    full = np.stack([embed_text(retrieval.chunk_text(row)) for row in entries]).astype(np.float16)
    summary = np.stack([embed_text(f"{row['name']}\n{row['summary']}") for row in entries]
                       ).astype(np.float16)
    np.save(directory / "emb_full.npy", full)
    np.save(directory / "emb_summary.npy", summary)
    BM25.build([retrieval.tokenize(retrieval.chunk_text(row)) for row in entries]
               ).save(directory / "bm25.npz")
    by_corpus = {}
    for row in entries:
        by_corpus[row["corpus"]] = by_corpus.get(row["corpus"], 0) + 1
    manifest = {"version": 2, "chunks": len(entries), "chunks_by_corpus": by_corpus,
                "embed_model": "tests/hashed-bag-of-words", "ollama_embed": "fake-embed",
                "ollama_llm": "fake-llm", "query_prefix": QUERY_PREFIX,
                "probe": {"text": PROBE_TEXT,
                          "vector": [round(float(x), 6) for x in embed_text(PROBE_TEXT)]}}
    (directory / "manifest.json").write_bytes(orjson.dumps(manifest))
    return directory


class FakeClient:
    """Stands in for Ollama. Replies are queued; every call is recorded."""

    def __init__(self, replies=(), pieces=("The ", "kobold ", "says: ", "ten minutes."),
                 base_url="http://fake-ollama:11434"):
        self.replies = list(replies)
        self.pieces = list(pieces)
        self.base_url = base_url
        self.calls: list[tuple] = []
        self.embedded: list[list[str]] = []
        self.closed = False

    def embed(self, texts, model, keep_alive=None):
        self.embedded.append(list(texts))
        return np.stack([embed_text(t.split(QUERY_PREFIX, 1)[-1]) for t in texts])

    def chat(self, system, user, model, max_tokens=700, keep_alive=None):
        self.calls.append((system, user, model, max_tokens))
        return self.replies.pop(0) if self.replies else ""

    def stream(self, system, user, model, max_tokens=700, keep_alive=None):
        self.calls.append((system, user, model, max_tokens))
        yield from self.pieces

    def close(self):
        self.closed = True


def plan_reply(summary: str = "", kinds: str = "", scope: str = "rules") -> str:
    return f"SUMMARY: {summary}\nKINDS: {kinds}\nSCOPE: {scope}"


@pytest.fixture(scope="session")
def index_dir(tmp_path_factory) -> pathlib.Path:
    return build_index(tmp_path_factory.mktemp("kobold-index"))


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def assistant(index_dir, client) -> Assistant:
    a = Assistant(index_dir, "http://fake-ollama:11434", llm_model="fake-llm")
    a.ollama.close()
    a.ollama = a.embed_client = client
    a._verified = True
    return a
