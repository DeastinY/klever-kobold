"""The runtime: a Pathfinder 2e rules assistant that runs on a laptop.

Everything heavy is delegated to Ollama over HTTP, so this package needs only
numpy, httpx and orjson -- no torch, no transformers, no CUDA. On a 16 GB
MacBook the resident cost is the two models Ollama holds (about 6.3 GB) plus
roughly 460 MB of memory-mapped index (250 MB before the lore).

The pipeline is the one the benchmark measured, in order:

1. **Rewrite.** The question is turned into a hypothetical one-line entry summary
   and up to three entry kinds. Players describe situations; the index holds
   entities, and this is what bridges them. Worth +27 points of recall@5.
2. **Narrow.** Restrict to the suggested kinds when enough candidates survive.
   Equipment and creatures are two thirds of the corpus and answer almost
   nothing.
3. **Retrieve.** Fuse four rankings by reciprocal rank: BM25, dense over the full
   entry, dense over the one-line summary, and dense of the *hypothetical*
   summary against the summary index.
4. **Hop.** Any pre-Remaster entry that surfaces is replaced by the entry that
   superseded it, so legacy rules are never served as current.
5. **Answer.** The excerpts are given to the model as authoritative, with an
   instruction to cite the source URL and to say plainly when the answer is not
   among them.

Lore is a second corpus in the same index -- PathfinderWiki, one chunk per
article or section -- behind a **scope**. ``rules`` never sees it and is the
path every number in the docs was measured on; ``lore`` sees both corpora;
``auto`` (the default) lets the rewrite step say which, in one extra line, and
anything short of a plain "lore" means rules. So a rules question cannot be
answered from a wiki paragraph, and "who rules Cheliax?" gets the wiki.
A caller that passes ``history`` gets one stage in front of that: the follow-up
is condensed into a question that can be retrieved on its own, and the pipeline
below runs on the condensed question unchanged. Nothing here does that by
default -- no history, no condense call, byte-identical prompts. See
notes/followup-design.md.
"""

from __future__ import annotations

import copy
import os
import pathlib
import re
import sys
import time
from dataclasses import dataclass
from typing import Iterable, Iterator

import httpx
import numpy as np
import orjson

from . import retrieval
from .bm25 import BM25

DEFAULT_OLLAMA = "http://localhost:11434"

# Ollama evicts a model after five minutes idle by default. At a table, questions
# arrive in bursts separated by long gaps, and paying a 5.7 GB reload every time
# someone thinks of something is the difference between useful and abandoned.
KEEP_ALIVE = "2h"

# The 4B answers by default, everywhere. It scores 93/109 on the hand-written
# holdout against the 9B's 100 and runs at twice the speed in half the memory;
# in use the difference in speed is felt on every question and the seven items
# are not. The 9B stays one flag away (--llm-model qwen3.5:9b) and is the
# "Better" preset in the web UI. On a 16 GB laptop the 9B also makes the
# whole machine lag, which is where this started.
BIG_LLM = "qwen3.5:9b"
SMALL_LLM = "qwen3.5:4b"
DEFAULT_LLM = SMALL_LLM


def machine_memory_gb() -> float:
    """Physical memory in GiB (the number on the box), or 0.0 when it cannot be read (then nothing is assumed)."""
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
    except (AttributeError, ValueError, OSError):
        pass
    try:  # Windows
        import ctypes
        class Status(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        st = Status(); st.dwLength = ctypes.sizeof(Status)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        return st.ullTotalPhys / 2**30
    except Exception:
        return 0.0


def default_llm() -> tuple[str, str]:
    """The default answering model, and one line on it."""
    gb = machine_memory_gb()
    room = (f"; this machine's {gb:.0f} GB would fit it" if gb >= 20 else
            f"; on this machine's {gb:.0f} GB it makes everything lag" if gb else "")
    return DEFAULT_LLM, (f"{DEFAULT_LLM} — the default (93/109 on the holdout, twice the 9B's "
                         f"speed). --llm-model {BIG_LLM} for the 9B, 100/109{room}.")


INDEX_URL = ("https://github.com/DeastinY/klever-kobold/releases/download/"
             "index-v2/kobold-index.tar.gz")


def default_index() -> pathlib.Path:
    """Where the index lives, whether this is a clone or an installed tool.

    Running from a checkout, ``dist/kobold-index`` is right there. Installed with
    ``uv tool install`` or run with ``uvx``, the package sits in a cache that is
    wiped on upgrade, so a 460 MB index cannot live beside it -- it goes to the
    user data directory instead and survives.
    """
    repo = pathlib.Path(__file__).resolve().parents[2] / "dist" / "kobold-index"
    if (repo / "manifest.json").exists():
        return repo
    env = os.environ.get("KOBOLD_INDEX")
    if env:
        return pathlib.Path(env).expanduser()
    if sys.platform == "darwin":
        base = pathlib.Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = pathlib.Path(os.environ.get("LOCALAPPDATA", pathlib.Path.home()))
    else:
        base = pathlib.Path(os.environ.get("XDG_DATA_HOME",
                                           pathlib.Path.home() / ".local" / "share"))
    new = base / "kleverkobold" / "kobold-index"
    # Installs from before the rename keep working: an index under the old
    # names is moved to the new ones once, and never looked for again.
    old = base / "pf2etune" / "pf2e-index"
    if not new.exists() and (old / "manifest.json").exists():
        try:
            new.parent.mkdir(parents=True, exist_ok=True)
            old.rename(new)
        except OSError:
            return old
    return new


DEFAULT_INDEX = default_index()

CATEGORIES = ("action", "condition", "feat", "spell", "equipment", "weapon", "armor",
              "creature", "hazard", "trait", "rules", "class-feature", "ritual",
              "archetype", "background", "heritage", "deity", "shield")

# What a question may be answered from. ``rules`` is the Archives alone and is
# the measured path; ``lore`` adds PathfinderWiki; ``auto`` asks the rewriter.
SCOPES = ("auto", "rules", "lore")
DEFAULT_SCOPE = "auto"

# Excerpts kept for the Archives when a question is answered with lore in play.
# The wiki has 1,571 deity pages and the Archives one entry per god, so "which
# domains does Pharasma grant?" -- a mechanics question the rewriter reads as
# lore -- came back with eight wiki excerpts and no stat block. Two slots keep
# the entry the answer lives in; they are filled only from Archives entries that
# retrieval ranked in the top k on its own, so a pure lore question ("who rules
# Cheliax?") is not charged for them unless the Archives had a real candidate.
RULES_SLOTS = 2

REWRITE_SYSTEM = (
    "You help search a Pathfinder 2e rules database. Each entry is one game element with a "
    "one-line summary.\n\n"
    "Given a player's question, reply with exactly two lines and nothing else:\n"
    "SUMMARY: the one-line summary you would expect on the database entry that answers this "
    "question, written the way the rulebook writes summaries. Describe what it does. Do not "
    "guess at a name.\n"
    "KINDS: up to three entry kinds that could answer it, comma separated, from: "
    + ", ".join(CATEGORIES) + "\n\n"
    "Question: An ogre has grabbed my monk. What can she do about it on her turn?\n"
    "SUMMARY: Attempt to escape from being grabbed, immobilized, or restrained.\n"
    "KINDS: action, condition\n\n"
    "Question: Is there a feat that makes falling less dangerous?\n"
    "SUMMARY: Treat falls as shorter than they are.\n"
    "KINDS: feat\n\n"
    "Question: How much healing does a short rest give my party?\n"
    "SUMMARY: Spend 10 minutes treating an injured creature to restore Hit Points.\n"
    "KINDS: action, feat"
)

# The same prompt with one more line, used only when the index carries lore.
# The rules-only prompt above is what the holdout was measured with and stays
# byte-identical on an index without lore; this one keeps its SUMMARY and KINDS
# instructions and examples word for word and adds SCOPE after them, so a
# wrong-scope failure is separable from a rewrite failure.
REWRITE_SCOPE_SYSTEM = (
    "You help search a Pathfinder 2e reference. Rules entries come from the Archives of "
    "Nethys: each is one game element with a one-line summary. Setting lore comes from "
    "PathfinderWiki: one article per person, place, deity, organization or event of Golarion.\n\n"
    "Given a player's question, reply with exactly three lines and nothing else:\n"
    "SUMMARY: the one-line summary you would expect on the database entry that answers this "
    "question, written the way the rulebook writes summaries. Describe what it does. Do not "
    "guess at a name.\n"
    "KINDS: up to three entry kinds that could answer it, comma separated, from: "
    + ", ".join(CATEGORIES) + "; or none.\n"
    "SCOPE: rules if the question is about how the game works (mechanics, numbers, what a "
    "character can do, what a feat, spell, item or creature does; a creature's level, traits, "
    "rarity or stat block is rules even when the creature has a personal name); lore if it is "
    "about the setting (who someone is, where a place is, history, gods and their followers, "
    "what a nation or city is like). When in doubt, rules.\n\n"
    "Question: An ogre has grabbed my monk. What can she do about it on her turn?\n"
    "SUMMARY: Attempt to escape from being grabbed, immobilized, or restrained.\n"
    "KINDS: action, condition\n"
    "SCOPE: rules\n\n"
    "Question: Is there a feat that makes falling less dangerous?\n"
    "SUMMARY: Treat falls as shorter than they are.\n"
    "KINDS: feat\n"
    "SCOPE: rules\n\n"
    "Question: How much healing does a short rest give my party?\n"
    "SUMMARY: Spend 10 minutes treating an injured creature to restore Hit Points.\n"
    "KINDS: action, feat\n"
    "SCOPE: rules\n\n"
    "Question: What level is the creature Daring Danika?\n"
    "SUMMARY: A stat block for a named human performer with an acrobatic fighting style.\n"
    "KINDS: creature\n"
    "SCOPE: rules\n\n"
    "Question: Who rules Cheliax these days?\n"
    "SUMMARY: Cheliax is a diabolist empire ruled by House Thrune from the capital of Egorian.\n"
    "KINDS: none\n"
    "SCOPE: lore\n\n"
    "Question: Which goddess do travellers and dreamers pray to?\n"
    "SUMMARY: Desna is the goddess of dreams, luck, stars, and travellers.\n"
    "KINDS: deity\n"
    "SCOPE: lore"
)

RERANK_SYSTEM = (
    "You are selecting which Archives of Nethys entries could answer a Pathfinder 2e question.\n"
    "You will see a numbered list of candidate entries, each with its kind and a one-line summary, "
    "then the question.\n"
    "Reply with the numbers of the entries most likely to contain the answer, best first, comma "
    "separated, at most {k}. Include an entry if it is plausibly relevant; the cost of a wrong "
    "inclusion is low and the cost of dropping the answer is high.\n"
    "Reply with numbers only. No words, no explanation."
)

ANSWER_SYSTEM = (
    "You are answering questions about the Pathfinder Second Edition tabletop roleplaying game. "
    "Rules excerpts from the Archives of Nethys are provided below. Treat them as authoritative "
    "and prefer them over your own recollection. If the excerpts do not contain the answer, say "
    "so plainly rather than guessing.\n"
    "Keep the answer under 120 words: lead with the direct answer, then the key numbers or "
    "conditions. No headings, and no bullet list unless the question asks for a list. Finish "
    "with a line 'Source:' giving the URL of each excerpt you used, and nothing after it."
)

# Used only when a lore excerpt is among the eight. A lore answer is a short
# paragraph about a person or a place, not a stat block, so the budget is a
# little longer and the "key numbers" line is replaced with who-where-when.
LORE_ANSWER_SYSTEM = (
    "You are answering questions about the Pathfinder Second Edition tabletop roleplaying game "
    "and its setting, the world of Golarion. Excerpts are provided below: rules entries from the "
    "Archives of Nethys and setting lore from PathfinderWiki, each marked. Treat them as "
    "authoritative and prefer them over your own recollection. If the excerpts do not contain "
    "the answer, say so plainly rather than guessing.\n"
    "Keep the answer under 150 words: lead with the direct answer, then the details that "
    "matter -- who, where, when, and how it bears on play if the question is about a game. No "
    "headings, and no bullet list unless the question asks for a list. Finish with a line "
    "'Source:' giving the URL of each excerpt you used, and nothing after it."
)

# Follow-ups are elliptical -- "what if she's prone?" names nothing the index
# holds, and BM25 has three stopwords to work with. Condensing restores the
# names before retrieval sees the question, and is a separate call from the
# rewriter on purpose: one job each, so a bad answer can be blamed on the stage
# that produced it by reading two short strings.
CONDENSE_SYSTEM = (
    "You rewrite follow-up questions in a Pathfinder 2e rules conversation so they can be "
    "understood on their own.\n\n"
    "You are given the exchange before it and a new question. Reply with one line and nothing "
    "else: the new question, rewritten so someone who has not read the conversation could look "
    "the answer up. Put back the names that were called 'it', 'she' or 'that', and keep what "
    "the asker actually wants to know. Do not answer it, do not explain it, and do not add "
    "rules nobody asked about. If the new question already stands on its own, reply with it "
    "unchanged.\n\n"
    "Earlier question: How does Treat Wounds work?\n"
    "Earlier answer: Treat Wounds is a 10-minute Medicine activity; attempt a DC 15 Medicine "
    "check and the target regains 2d8 Hit Points on a success.\n"
    "New question: what if she's untrained\n"
    "Rewritten: What happens when a character untrained in Medicine attempts Treat Wounds?\n\n"
    "Earlier question: What does the grabbed condition do?\n"
    "Earlier answer: Grabbed makes you immobilized and off-guard, and you must succeed at a "
    "DC 5 flat check to use an action with the manipulate trait.\n"
    "New question: and can I still cast\n"
    "Rewritten: Can a grabbed creature still cast spells?\n\n"
    "Earlier question: How much does a longsword cost?\n"
    "Earlier answer: A longsword costs 1 gp.\n"
    "New question: What level is Battle Medicine?\n"
    "Rewritten: What level is Battle Medicine?"
)

# Added to ANSWER_SYSTEM only when there is an earlier turn in the prompt. The
# single-turn system string stays exactly the one the holdout was measured with.
FOLLOWUP_NOTE = (
    "\nThe earlier exchange above the excerpts is context for what the question refers to. "
    "Answer the last question. The earlier answer is not a source: cite only the excerpts."
)

RE_NETHYS_NOTE = re.compile(r"^[ \t]*_?\*?Nethys Note:[^\n]*\n?", re.M | re.I)
RE_CLEAN = re.compile(r"^[\s\-*\d.)]+|[\s;:]+$")


def parse_plan(raw: str) -> dict:
    """The rewriter's reply as a plan: summary, entry kinds, and scope.

    Scope is "lore" only when the line says so outright; a missing line, a
    hedge, or a reply from the rules-only prompt all read as rules. That is the
    direction the mistake is allowed to go in.
    """
    summary, kinds, scope = "", [], "rules"
    for line in (raw or "").splitlines():
        line = line.strip()
        if line.upper().startswith("SUMMARY:"):
            summary = RE_CLEAN.sub("", line.split(":", 1)[1]).strip()
        elif line.upper().startswith("KINDS:"):
            for part in line.split(":", 1)[1].split(","):
                part = part.strip().lower().replace(" ", "-")
                if part in CATEGORIES and part not in kinds:
                    kinds.append(part)
        elif line.upper().startswith("SCOPE:"):
            if line.split(":", 1)[1].strip().lower().rstrip(".") == "lore":
                scope = "lore"
    return {"summary": summary[:220], "categories": kinds[:3], "scope": scope}

# The TREC default of 60 flattens rank differences almost to nothing when fusing a
# handful of 50-item rankings: rank 1 scores 0.0164 and rank 10 scores 0.0143.
# Swept on the holdout; 5 was best, though the margin is inside the noise of a
# 48-item sample.
RRF_SMOOTHING = 5

# Characters of each retrieved entry put in front of the model. Swept on the
# holdout; see notes/experiments.md.
CONTEXT_CHARS = 1600

# Characters of the previous answer carried into a follow-up -- into the
# condense prompt, and into the answering prompt. ANSWER_SYSTEM budgets 120
# words; 19 real answers from the 4B came out at a median of 651 characters and
# a maximum of 1,027, and this keeps 17 of the 19 whole. What the tail costs is
# context, not correctness: both readers want the entity names, and those are
# in the first sentence. Nothing else from the previous turn travels -- not its
# excerpts and not its sources. notes/followup-design.md says why.
HISTORY_CHARS = 900

# Safety net on generated answer length, not the thing that ends a normal answer.
# Length is set by the prompt: told only to "answer concisely", Qwen3.5-9B wrote
# 458 tokens of bulleted restatement for "How does Treat Wounds work?", 37 s of a
# 52 s answer on an M3 laptop; given a 120-word budget it wrote 156 and still
# finished on the source line. A cap that bites cuts mid-sentence and drops the
# citation, so this sits well above the budget and only catches runaways.
ANSWER_TOKENS = 400

# Excerpts per answer. Swept end-to-end on the hand-written holdout: 5 -> 81.7%,
# 8 -> 85.3%, 12 -> 80.7%. The curve is an inverted U -- recall@20 is higher than
# recall@5, so more excerpts keep finding the answer, until enough irrelevant ones
# accumulate to drown it.
DEFAULT_K = 8

# Candidates handed to the reranker before it cuts down to DEFAULT_K.
#
# Reranking is on by default on a split decision. It is flat on the hand-written
# gate (89.9% either way) and worth +6.0 points of recall@8 on the 300 mined
# questions, which is eighteen items and well outside that set's noise. It also
# takes false-premise questions to 19/19. It costs about a tenth of a second per
# query and three points of descriptive accuracy, so it is a real trade rather
# than a free win -- pass rerank=False to turn it off.
DEFAULT_POOL = 24

# One-hop link expansion: off, having been measured and rejected.
#
# The hypothesis was good. Judged answerability said retrieval finds the right
# *topic* and not the specific rule, those questions are about interactions, and a
# topic page almost always links to the specific rule involved -- the corpus keeps
# 394,598 resolved outbound links. Tuned to parity on the gate it was still 4.7
# points *worse* on judged answerability, the metric it was built for. Links are a
# weaker relevance signal than they look: a rules page cites everything adjacent,
# so expansion adds the neighbourhood rather than the answer.
#
# The code and the packaged graph stay; multi-hop over a *reasoned* path, rather
# than a blanket one-hop pull, is still untried.
DEFAULT_EXPAND = 0
# Link evidence is weaker than direct match: it says "the topic page mentions
# this", not "this matches the query".
EXPAND_WEIGHT = 0.25


class OllamaError(RuntimeError):
    """Raised with a message a user can act on, not a stack trace."""


@dataclass
class Hit:
    chunk_id: str
    name: str
    category: str
    level: object
    url: str
    text: str
    summary: str = ""
    legacy_name: list = None  # names this entry had before the Remaster, if any
    corpus: str = "aon"       # "aon" (rules) or "pathfinderwiki" (lore)

    @property
    def lore(self) -> bool:
        return self.corpus == "pathfinderwiki"


@dataclass
class Turn:
    """One earlier exchange, as the next question needs to see it.

    ``standalone`` is the condensed form of ``question`` -- what the last
    condense call produced. Handing *that* back rather than the raw text is
    what makes a chain of three follow-ups work: turn three condenses against
    a turn-two question that already names its subject, so "and untrained?"
    can still find its way back to Treat Wounds without anyone carrying the
    whole transcript.
    """

    question: str
    answer: str = ""
    standalone: str = ""

    def asked(self) -> str:
        """The form the next turn should be condensed against."""
        return self.standalone or self.question


class OpenAICompatible:
    """Any server speaking the OpenAI API: mlx-serve, vllm-mlx, LM Studio, llama.cpp.

    Ollama is the default because it installs in one command and, since 0.19,
    uses MLX on Apple Silicon anyway. This exists for the cases it does not
    cover -- a model Ollama has no build of, an already-running LM Studio, or a
    server tuned harder than Ollama's defaults.

    The embedding model is not interchangeable. The index was built with one
    specific encoder and querying it with another produces vectors in a different
    space, which does not error -- it just quietly returns nonsense. `verify_probe`
    exists to make that loud.
    """

    def __init__(self, base_url: str, api_key: str = "not-needed",
                 timeout: float | None = 180.0) -> None:
        self.base_url = base_url.rstrip("/")
        # Every published OpenAI-compatible base URL ends in /v1 and every path
        # here starts with it, so the obvious paste produces /v1/v1/chat. Nobody
        # serves a real endpoint under a second /v1, so strip it rather than
        # returning a 404 the user has to decode.
        if self.base_url.endswith("/v1"):
            self.base_url = self.base_url[:-3]
        self._client = httpx.Client(timeout=timeout,
                                    headers={"Authorization": f"Bearer {api_key}"})

    def close(self) -> None:
        self._client.close()

    def _post(self, path: str, body: dict) -> dict:
        try:
            r = self._client.post(f"{self.base_url}{path}", json=body)
        except httpx.ConnectError as exc:
            raise OllamaError(f"Cannot reach an OpenAI-compatible server at "
                              f"{self.base_url}.") from exc
        if r.status_code >= 400:
            raise OllamaError(f"{self.base_url}{path} returned {r.status_code}: "
                              f"{r.text[:200]}")
        return orjson.loads(r.content)

    def embed(self, texts: list[str], model: str, keep_alive: str = KEEP_ALIVE) -> np.ndarray:
        data = self._post("/v1/embeddings", {"model": model, "input": texts})
        vecs = np.asarray([d["embedding"] for d in data["data"]], dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / np.where(norms == 0, 1, norms)

    def chat(self, system: str, user: str, model: str, max_tokens: int = 700,
             keep_alive: str = KEEP_ALIVE) -> str:
        data = self._post("/v1/chat/completions", {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": 0,
            "max_tokens": max_tokens,
            "stream": False,
        })
        return (data["choices"][0]["message"].get("content") or "").strip()

    def stream(self, system: str, user: str, model: str, max_tokens: int = 700,
               keep_alive: str = KEEP_ALIVE) -> Iterator[str]:
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": 0, "max_tokens": max_tokens, "stream": True,
        }
        try:
            with self._client.stream("POST", f"{self.base_url}/v1/chat/completions",
                                     json=body) as r:
                if r.status_code >= 400:
                    raise OllamaError(f"{self.base_url}/v1/chat/completions returned "
                                      f"{r.status_code}")
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    delta = orjson.loads(payload)["choices"][0].get("delta") or {}
                    if delta.get("content"):
                        yield delta["content"]
        except httpx.ConnectError as exc:
            raise OllamaError(f"Cannot reach an OpenAI-compatible server at "
                              f"{self.base_url}.") from exc


class Ollama:
    def __init__(self, base_url: str = DEFAULT_OLLAMA, timeout: float | None = 180.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def _post(self, path: str, body: dict) -> dict:
        try:
            r = self._client.post(f"{self.base_url}{path}", json=body)
        except httpx.ConnectError as exc:
            raise OllamaError(
                f"Cannot reach Ollama at {self.base_url}. Start it with `ollama serve`."
            ) from exc
        if r.status_code == 404:
            raise OllamaError(
                f"Ollama does not have the model {body.get('model')!r}. "
                f"Pull it with `ollama pull {body.get('model')}`."
            )
        r.raise_for_status()
        return orjson.loads(r.content)

    def embed(self, texts: list[str], model: str,
              keep_alive: str = KEEP_ALIVE) -> np.ndarray:
        data = self._post("/api/embed",
                          {"model": model, "input": texts, "keep_alive": keep_alive})
        vecs = np.asarray(data["embeddings"], dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / np.where(norms == 0, 1, norms)

    def _body(self, system: str, user: str, model: str, max_tokens: int,
              keep_alive: str, stream: bool) -> dict:
        return {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": stream,
            "think": False,
            "keep_alive": keep_alive,
            "options": {"temperature": 0, "num_predict": max_tokens},
        }

    def chat(self, system: str, user: str, model: str, max_tokens: int = 700,
             keep_alive: str = KEEP_ALIVE) -> str:
        data = self._post("/api/chat",
                          self._body(system, user, model, max_tokens, keep_alive, False))
        return (data.get("message") or {}).get("content", "").strip()

    def stream(self, system: str, user: str, model: str, max_tokens: int = 700,
               keep_alive: str = KEEP_ALIVE) -> Iterator[str]:
        """Yield answer text as it is generated.

        On a laptop the answer is decoded at ~15 tokens/second, so a 300-token
        reply is twenty seconds during which a non-streaming UI shows nothing at
        all. The total does not change; what changes is that the first sentence
        arrives while the rest is still being written.
        """
        body = self._body(system, user, model, max_tokens, keep_alive, True)
        try:
            with self._client.stream("POST", f"{self.base_url}/api/chat", json=body) as r:
                if r.status_code == 404:
                    raise OllamaError(
                        f"Ollama does not have the model {model!r}. "
                        f"Pull it with `ollama pull {model}`.")
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    chunk = orjson.loads(line)
                    piece = (chunk.get("message") or {}).get("content") or ""
                    if piece:
                        yield piece
                    if chunk.get("done"):
                        break
        except httpx.ConnectError as exc:
            raise OllamaError(
                f"Cannot reach Ollama at {self.base_url}. Start it with `ollama serve`."
            ) from exc


def client_for(backend: str, base_url: str, api_key: str | None = None,
               timeout: float | None = 180.0):
    """The HTTP client for a backend name. One place, so overrides agree with startup."""
    if backend == "openai":
        return OpenAICompatible(base_url, api_key or "not-needed", timeout=timeout)
    return Ollama(base_url, timeout=timeout)


def probe_backend(backend: str, base_url: str, api_key: str | None = None,
                  timeout: float = 8.0) -> list[str]:
    """The model names a backend is currently serving, sorted.

    Two callers: "test connection", and the settings panel's model list, so a
    model can be picked rather than typed from memory. The key is used for the
    one request and discarded -- it is never returned, stored or logged, and
    response bodies are deliberately left out of error messages so a provider
    that echoes credentials back in an error cannot leak them onward.
    """
    base = base_url.rstrip("/")
    headers: dict[str, str] = {}
    if backend == "openai":
        if base.endswith("/v1"):
            base = base[:-3]
        url = f"{base}/v1/models"
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
    else:
        url = f"{base}/api/tags"
    try:
        r = httpx.get(url, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        raise OllamaError(f"Cannot reach {url} ({type(exc).__name__}).") from exc
    if r.status_code >= 400:
        detail = " — check the API key" if r.status_code in (401, 403) else ""
        raise OllamaError(f"{url} returned {r.status_code}{detail}.")
    try:
        data = orjson.loads(r.content)
    except orjson.JSONDecodeError as exc:
        raise OllamaError(f"{url} did not return JSON; is that the right base URL?") from exc
    if backend == "openai":
        rows = data.get("data") or []
        return sorted({str(m.get("id")) for m in rows if isinstance(m, dict) and m.get("id")})
    rows = data.get("models") or []
    return sorted({str(m.get("name")) for m in rows if isinstance(m, dict) and m.get("name")})


class Assistant:
    def __init__(self, index_dir: pathlib.Path = DEFAULT_INDEX,
                 ollama_url: str = DEFAULT_OLLAMA, backend: str = "ollama",
                 llm_model: str | None = None, embed_model: str | None = None,
                 context_chars: int = CONTEXT_CHARS,
                 answer_tokens: int = ANSWER_TOKENS,
                 api_key: str | None = None) -> None:
        index_dir = pathlib.Path(index_dir)
        if not (index_dir / "manifest.json").exists():
            raise OllamaError(
                f"No index at {index_dir}.\n"
                f"Fetch it with:  kobold setup\n"
                f"or point --index at an unpacked kobold-index directory."
            )
        self.manifest = orjson.loads((index_dir / "manifest.json").read_bytes())
        self.ollama = client_for(backend, ollama_url, api_key)
        # Answering and embedding are separable: a variant can send the answer to
        # someone else's model while retrieval keeps talking to the encoder that
        # built the index. They start as the same client, which is the single-
        # backend case and costs nothing.
        self.embed_client = self.ollama
        self.backend = backend
        self.base_url = self.ollama.base_url
        self.context_chars = context_chars
        self.answer_tokens = answer_tokens
        # Eval-only override: the rewrite prompt to use regardless of the index.
        # Lets the gate isolate the cost of the SCOPE line from the lore rows.
        self.rewrite_system: str | None = None
        self._verified = False
        if llm_model:
            self.manifest["ollama_llm"] = llm_model
        if embed_model:
            self.manifest["ollama_embed"] = embed_model

        meta = [orjson.loads(l) for l in (index_dir / "meta.jsonl").open("rb")]

        # Entry bodies are 48 MB of JSON that becomes ~500 MB of Python strings if
        # parsed eagerly, for the sake of the eight entries an answer actually
        # quotes. Index byte offsets instead and read those eight on demand.
        self._bodies_path = index_dir / "bodies.jsonl"
        self._body_offsets: dict[str, tuple[int, int]] = {}
        with self._bodies_path.open("rb") as fh:
            offset = 0
            for line in fh:
                # The id is the first field, so it can be found without parsing.
                start = line.index(b'"id":"') + 6
                chunk_id = line[start:line.index(b'"', start)].decode()
                self._body_offsets[chunk_id] = (offset, len(line))
                offset += len(line)

        # mmap: the embeddings are read a few thousand rows at a time, so the OS
        # page cache does a better job than loading 170 MB up front.
        full = np.load(index_dir / "emb_full.npy", mmap_mode="r")
        summary = np.load(index_dir / "emb_summary.npy", mmap_mode="r")
        self.index = retrieval.Index(
            ids=[m["id"] for m in meta], meta=meta,
            embeddings=full, summary_embeddings=summary,
            bm25=BM25.load(index_dir / "bm25.npz"),
            model_name=self.manifest["embed_model"],
        )
        # One mask per scope, built once: `allowed` walks every row.
        self._masks = {False: self.index.allowed(exclude_legacy=False),
                       True: self.index.allowed(exclude_legacy=False, lore=True)}
        self._base_mask = self._masks[False]

        # Outbound link graph, if the package carries one. Optional so an older
        # index still loads.
        self._links: dict[int, list[int]] = {}
        graph = index_dir / "links.jsonl"
        if graph.exists():
            for line in graph.open("rb"):
                row = orjson.loads(line)
                src = self.index.position(row["id"])
                if src is None:
                    continue
                targets = [p for p in (self.index.position(t) for t in row["to"])
                           if p is not None]
                if targets:
                    self._links[src] = targets

    def variant(self, backend: str, base_url: str, llm_model: str = "",
                api_key: str | None = None, context_chars: int | None = None,
                answer_tokens: int | None = None,
                remote_embedder: bool = False) -> "Assistant":
        """A second Assistant over the *same* loaded index, answering elsewhere.

        The index is 460 MB of memory-mapped arrays, a BM25 matrix and 73,922
        metadata rows; rebuilding that because someone changed a model name in
        the settings panel would cost a second and the memory twice over. A
        shallow copy shares all of it by reference -- every shared attribute is
        read-only once ``__init__`` has run -- and only the HTTP client, the
        model names and the two length caps differ.

        ``remote_embedder`` is the dangerous switch and defaults off. Retrieval
        normally keeps using the encoder this server started with and already
        verified against the index fingerprint, so pointing the answer at
        someone else's model cannot quietly change what is retrieved. Turned on,
        ``require_embedder`` gates the first request instead.
        """
        clone = copy.copy(self)
        clone.manifest = dict(self.manifest)   # so an override does not leak into the base
        if llm_model:
            clone.manifest["ollama_llm"] = llm_model
        clone.ollama = client_for(backend, base_url, api_key)
        clone.backend = backend
        clone.base_url = clone.ollama.base_url
        clone.embed_client = clone.ollama if remote_embedder else self.embed_client
        if context_chars:
            clone.context_chars = context_chars
        if answer_tokens:
            clone.answer_tokens = answer_tokens
        # A shared embedder is whatever the base already proved at startup; a
        # remote one has proved nothing yet.
        clone._verified = self._verified and not remote_embedder
        return clone

    def close(self) -> None:
        """Release this configuration's HTTP client. The shared index is untouched.

        Only ever called on a variant: closing the client of the Assistant the
        server started with would take the whole page down with it.
        """
        self.ollama.close()

    def body(self, chunk_id: str) -> str:
        span = self._body_offsets.get(chunk_id)
        if span is None:
            return ""
        offset, length = span
        with self._bodies_path.open("rb") as fh:
            fh.seek(offset)
            return orjson.loads(fh.read(length)).get("text", "")

    def verify_embedder(self) -> tuple[bool, float]:
        """Check the query encoder matches the one that built the index.

        The manifest stores the embedding of a fixed probe string. If the running
        encoder is a different model the cosine collapses, and catching that here
        turns a silent quality failure -- retrieval that returns plausible,
        unrelated entries -- into a message at startup.
        """
        probe = self.manifest.get("probe")
        if not probe:
            return True, 1.0
        vec = self._embed_queries([probe["text"]])[0]
        expected = np.asarray(probe["vector"], dtype=np.float32)
        if vec.shape != expected.shape:
            # A different encoder family: different width, so not even comparable.
            # This is the common shape of the mistake and deserves its own answer
            # rather than a matmul traceback.
            return False, 0.0
        return float(vec @ expected) >= 0.95, float(vec @ expected)

    def _mismatch_message(self, similarity: float) -> str:
        detail = ("dimensions differ" if similarity == 0.0
                  else f"similarity {similarity:.2f}, expected ~1.00")
        return (f"The embedding model does not match the one this index was built "
                f"with ({detail}).\n"
                f"  Index built with: {self.manifest['embed_model']}\n"
                f"  Serving now:      {self.manifest['ollama_embed']} at {self.embed_client.base_url}\n"
                f"Retrieval would return plausible but unrelated entries.")

    def require_embedder(self) -> None:
        """Refuse to retrieve through an encoder that has not been checked.

        Idempotent and cached: the fingerprint probe is a model call, and paying
        it on every question would be absurd. A configuration that fails stays
        unverified and fails the same way on the next request, which is what the
        settings panel needs in order to keep showing the error.
        """
        if self._verified:
            return
        try:
            ok, similarity = self.verify_embedder()
        except OllamaError:
            raise
        except Exception as exc:
            # A backend that answers but cannot embed -- an OpenAI-compatible
            # server with only chat models, or Ollama handed a chat model as an
            # encoder -- fails somewhere inside httpx. Name the thing that is
            # missing instead of showing the page a status code.
            raise OllamaError(
                f"{self.embed_client.base_url} could not embed with "
                f"{self.manifest['ollama_embed']!r} ({type(exc).__name__}).\n"
                f"That backend has to serve the encoder this index was built with, "
                f"or leave the embedder set to this server's own.") from exc
        if not ok:
            raise OllamaError(self._mismatch_message(similarity))
        self._verified = True

    def warmup(self, progress=None) -> dict:
        """Make both models resident before anyone asks a question.

        On a laptop the first request pays for reading several gigabytes off
        disk. Doing that lazily means the first thing a new user sees is an
        unresponsive page with no explanation, which is how this was reported.
        """
        timings = {}
        for label, call in (
            ("embedding model", lambda: self.embed_client.embed(
                ["warmup"], self.manifest["ollama_embed"])),
            ("language model", lambda: self.ollama.chat("Reply with: ok", "ok",
                                                        self.manifest["ollama_llm"],
                                                        max_tokens=4)),
        ):
            if progress:
                progress(label, None)
            started = time.time()
            call()
            timings[label] = time.time() - started
            if progress:
                progress(label, timings[label])

        ok, similarity = self.verify_embedder()
        if not ok:
            raise OllamaError(self._mismatch_message(similarity))
        self._verified = True
        return timings

    # --- pipeline ------------------------------------------------------------

    @property
    def has_lore(self) -> bool:
        return bool(getattr(getattr(self, "index", None), "has_lore", False))

    def rewrite(self, question: str) -> dict:
        system = self.rewrite_system or (REWRITE_SCOPE_SYSTEM if self.has_lore else REWRITE_SYSTEM)
        try:
            # One more line to write on a lore index; the rules-only call is untouched.
            raw = self.ollama.chat(system, f"Question: {question}",
                                   self.manifest["ollama_llm"],
                                   max_tokens=100 if self.has_lore else 90)
        except OllamaError:
            raise
        except Exception:
            return {"summary": "", "categories": [], "scope": "rules"}
        return parse_plan(raw)

    def resolve_scope(self, scope: str, plan: dict | None) -> bool:
        """Whether this question may see lore. Anything unsure is rules."""
        if scope not in SCOPES:
            raise ValueError(f"scope must be one of {SCOPES}, not {scope!r}")
        if not self.has_lore or scope == "rules":
            return False
        if scope == "lore":
            return True
        return bool(plan) and plan.get("scope") == "lore"

    def condense(self, question: str, history: Iterable[Turn]) -> str:
        """Rewrite a follow-up into a question that can be retrieved on its own.

        Only the most recent turn is shown, and only its text. That is enough
        because the turn carries its own condensed form: the question it was
        answered as already names its subject, so a chain repairs itself one
        link at a time instead of growing a transcript in the prompt.

        Every failure returns the question untouched, which is exactly today's
        behaviour -- so the worst a broken condense call can do is leave a
        follow-up as badly retrieved as it already is.
        """
        prior = list(history)[-1:]
        if not prior:
            return question
        turn = prior[0]
        user = f"Earlier question: {turn.asked()[:400]}\n"
        if turn.answer:
            user += f"Earlier answer: {turn.answer[:HISTORY_CHARS]}\n"
        user += f"New question: {question}\nRewritten:"
        try:
            raw = self.ollama.chat(CONDENSE_SYSTEM, user, self.manifest["ollama_llm"],
                                   max_tokens=60)
        except OllamaError:
            raise
        except Exception:
            return question
        lines = [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]
        # The label is asked for and usually omitted, so prefer a labelled line
        # and fall back to the first thing said.
        line = next((ln for ln in lines if ln.lower().startswith("rewritten:")),
                    lines[0] if lines else "")
        if line.lower().startswith("rewritten:"):
            line = line.split(":", 1)[1]
        line = RE_CLEAN.sub("", line).strip().strip('"').strip("'").strip()
        # A condensation that lost the question, or ran on into an answer, is
        # worse than none: the raw follow-up at least says what was asked.
        if not line or len(line) > 300:
            return question
        return line

    def _embed_queries(self, texts: list[str]) -> np.ndarray:
        prefix = self.manifest["query_prefix"]
        return self.embed_client.embed([prefix + t for t in texts],
                                       self.manifest["ollama_embed"])

    def search(self, question: str, k: int = DEFAULT_K, plan: dict | None = None,
               rerank: bool = True, pool: int | None = None,
               expand: int = DEFAULT_EXPAND, scope: str = DEFAULT_SCOPE) -> list[Hit]:
        plan = plan if plan is not None else self.rewrite(question)
        queries = [question]
        if plan.get("summary"):
            queries.append(plan["summary"])
        vecs = self._embed_queries(queries).astype(np.float32)
        qvec, hvec = vecs[0], (vecs[1] if len(vecs) > 1 else None)

        lore = self.resolve_scope(scope, plan)
        mask = self._masks[lore]
        # Narrowing to the rewriter's entry kinds sharpens entity lookup and blinds
        # concept questions -- the rules chapters are excluded, and that is where
        # "is a critical failure a failure?" is answered. So both rankings are
        # kept and fused rather than one replacing the other. Costs one extra
        # scan of a memory-mapped matrix and no model call.
        narrow_mask = None
        if plan.get("categories"):
            narrowed = mask & self.index.allowed(exclude_legacy=False,
                                                 categories=plan["categories"], lore=lore)
            if narrowed.sum() >= k:
                narrow_mask = narrowed

        rankings = [self.index.dense(qvec, mask, 50),
                    self.index.dense(qvec, mask, 50, view="summary"),
                    self.index.lexical(question, mask, 50)]
        if hvec is not None:
            rankings.append(self.index.dense(hvec, mask, 50, view="summary"))
            rankings.append(self.index.dense(hvec, mask, 50))
        if narrow_mask is not None:
            rankings.append(self.index.dense(qvec, narrow_mask, 50))
            rankings.append(self.index.dense(qvec, narrow_mask, 50, view="summary"))
            rankings.append(self.index.lexical(question, narrow_mask, 50))
            if hvec is not None:
                rankings.append(self.index.dense(hvec, narrow_mask, 50, view="summary"))
        # An explicit pool wins even when this call is not reranking: `ask` runs
        # the rerank itself so it can time the stage, and still needs the deep
        # candidate list. Collapsing to k here silently disables reranking.
        take = pool or (DEFAULT_POOL if rerank else k)
        order = retrieval.rrf(rankings, max(take * 4, k * 4), smoothing=RRF_SMOOTHING,
                              index=self.index)

        if expand and self._links:
            # Walk one hop out from the best few results and fuse what they point
            # at as an additional ranking, ordered by the rank of the entry that
            # referred it. A topic page cites the specific rule; this is how the
            # specific rule becomes a candidate.
            referred: list[int] = []
            for seed in order[:expand]:
                for target in self._links.get(seed, ()):
                    if mask[target]:
                        referred.append(target)
            if referred:
                order = retrieval.rrf([order, referred], max(take * 4, k * 4),
                                      smoothing=RRF_SMOOTHING,
                                      weights=[1.0, EXPAND_WEIGHT], index=self.index)

        order = retrieval.follow_remaster(self.index, order)
        order = retrieval.dedupe(self.index, order)[:take]

        hits = [self._hit(i) for i in order]
        if rerank:
            hits = self.rerank(question, hits, k)
        if lore:
            # Two kinds of Archives entry qualify for a reserved slot: one the
            # question names outright ("Pharasma", so the deity's stat block),
            # and one retrieval put in its top k on its own. A trait that merely
            # shares a word with the question is neither, and was displacing a
            # lore page at rank eight.
            q = question.lower()
            pool = [self._hit(i) for i in order]
            eligible = [h for n, h in enumerate(pool)
                        if n < k or (len(h.name or "") >= 4 and h.name.lower() in q)]
            hits = self.keep_rules(hits, eligible, k)
        return hits

    @staticmethod
    def keep_rules(hits: list[Hit], candidates: list[Hit], k: int,
                   slots: int = RULES_SLOTS) -> list[Hit]:
        """Hold ``slots`` of ``k`` for the best Archives candidates when lore is in play.

        Only when the wiki has taken more than its share: a list that already
        carries two rules entries is returned as it is, and so is one where no
        rules entry was retrieved at all. Otherwise the lowest-ranked lore
        excerpts make room, so the stat block a mechanics question needs is in
        front of the model alongside the lore the rewriter thought it wanted.
        """
        top = hits[:k]
        rules = [h for h in top if not h.lore]
        if len(rules) >= slots:
            return top
        seen = {h.chunk_id for h in top}
        extra = [h for h in candidates if not h.lore and h.chunk_id not in seen][:slots - len(rules)]
        if not extra:
            return top
        lore_hits = [h for h in top if h.lore]
        keep = lore_hits[:max(0, k - len(rules) - len(extra))]
        # Keep the original order among what survives; the new rules entries
        # go last, next to the question, where a small model reads best.
        kept = {h.chunk_id for h in keep}
        return [h for h in top if not h.lore or h.chunk_id in kept] + extra

    def _hit(self, pos: int) -> Hit:
        m = self.index.meta[pos]
        old = m.get("legacy_name") or []
        old = [n for n in old if n] if isinstance(old, list) else [old]
        return Hit(chunk_id=self.index.ids[pos], name=m.get("name") or "",
                   category=m.get("category") or "", level=m.get("level"),
                   url=m.get("url") or "", text=self.body(self.index.ids[pos]),
                   summary=m.get("summary") or "", legacy_name=old,
                   corpus=m.get("corpus") or "aon")

    def rerank(self, question: str, hits: list[Hit], k: int) -> list[Hit]:
        """Reorder candidates with the model that is already loaded.

        A cross-encoder would be the textbook choice and would drag torch back
        into a runtime that currently needs numpy, httpx and orjson. The answering
        model is already resident, already knows the domain, and reads a list of
        one-line summaries in about a second -- and a separate probe had already
        shown the base model picks the right excerpt 80% of the time when that is
        all it has to do.

        Failure is designed to be free: anything the model does not mention keeps
        its fusion order behind the entries it did, so a garbled reply degrades to
        the ranking it was given.
        """
        if len(hits) <= k:
            return hits[:k]
        listing = "\n".join(
            f"{n}. {h.name} ({h.category.replace('-', ' ')}{', lore' if h.lore else ''})"
            + (f" [level {h.level}]" if h.level is not None else "")
            + f" — {(h.summary or h.text[:110]).strip()}"
            for n, h in enumerate(hits, 1))
        try:
            raw = self.ollama.chat(RERANK_SYSTEM.format(k=k),
                                   f"{listing}\n\nQuestion: {question}",
                                   self.manifest["ollama_llm"], max_tokens=60)
        except OllamaError:
            raise
        except Exception:
            return hits[:k]

        picked, seen = [], set()
        for token in re.findall(r"\d+", raw or ""):
            i = int(token) - 1
            if 0 <= i < len(hits) and i not in seen:
                seen.add(i)
                picked.append(hits[i])
        rest = [h for n, h in enumerate(hits) if n not in seen]
        return (picked + rest)[:k]

    def context(self, hits: Iterable[Hit], max_chars: int | None = None) -> str:
        max_chars = self.context_chars if max_chars is None else max_chars
        hits = list(hits)
        blocks = []
        for n, h in enumerate(hits, 1):
            head = f"[{n}] {h.name} ({h.category.replace('-', ' ')}"
            if h.level is not None:
                head += f", level {h.level}"
            if h.lore:
                head += ", Golarion lore from PathfinderWiki"
            head += f") — {h.url}"
            # The shipped index still carries AoN's "Nethys Note: No description…"
            # housekeeping line, which a small model reads as "does not exist".
            body = RE_NETHYS_NOTE.sub("", retrieval.plain(h.text))
            blocks.append(head + "\n" + body[:max_chars].strip())
        # The tag the rules path was measured with, unless lore is among them.
        tag = "excerpts" if any(h.lore for h in hits) else "rules_excerpts"
        return f"<{tag}>\n" + "\n\n".join(blocks) + f"\n</{tag}>"

    @staticmethod
    def system_for(hits: Iterable[Hit]) -> str:
        return LORE_ANSWER_SYSTEM if any(h.lore for h in hits) else ANSWER_SYSTEM

    def retrieve(self, question: str, k: int = DEFAULT_K, rerank: bool = True,
                 pool: int | None = None, expand: int = DEFAULT_EXPAND,
                 scope: str = DEFAULT_SCOPE,
                 history: Iterable[Turn] | None = None) -> tuple:
        """Everything up to the answer call, timed per stage.

        Split out from `ask` so the web UI can put sources on screen while the
        answer is still decoding, and so no caller has to run retrieval twice to
        get both halves of a result.

        With `history`, the follow-up is condensed first and every stage below
        runs on the condensed question -- rewrite, all four rankings, the
        rerank. The condensed form comes back on the plan as `standalone`,
        because the caller has to send it with the next turn, and because the
        one thing worth seeing when a follow-up goes wrong is what the kobold
        thought it was being asked.
        """
        timings: dict[str, float] = {}
        asked = question
        if history:
            t = time.time()
            asked = self.condense(question, history)
            timings["condense"] = round(time.time() - t, 2)

        t = time.time()
        plan = self.rewrite(asked)
        # What the question was actually answered from, for the caller to show.
        plan["lore"] = self.resolve_scope(scope, plan)
        timings["rewrite"] = round(time.time() - t, 2)
        if history:
            plan["standalone"] = asked

        t = time.time()
        hits = self.search(asked, k=k, plan=plan, rerank=False,
                           pool=pool or DEFAULT_POOL, expand=expand, scope=scope)
        timings["retrieve"] = round(time.time() - t, 2)

        if rerank:
            t = time.time()
            hits = self.rerank(asked, hits, k)
            timings["rerank"] = round(time.time() - t, 2)
        return plan, hits[:k], timings

    def earlier(self, history: Iterable[Turn] | None) -> str:
        """The previous turn as prompt text, or nothing at all.

        It goes *before* the excerpts, not between them and the question. A
        single-turn prompt ends with the entry the question names sitting next
        to the question (see `named_last`), and a conversation block wedged in
        there would undo an effect that was worth the difference between
        "level 12" and "no such creature exists".
        """
        prior = list(history or [])[-1:]
        if not prior:
            return ""
        turn = prior[0]
        block = f"Question: {turn.question[:400]}"
        if turn.answer:
            block += f"\nAnswer: {turn.answer[:HISTORY_CHARS]}"
        return "<earlier_exchange>\n" + block + "\n</earlier_exchange>\n\n"

    def answer_system(self, history: Iterable[Turn] | None = None,
                      hits: Iterable[Hit] = ()) -> str:
        """The answering instructions. Unchanged, to the byte, without history or lore."""
        base = self.system_for(hits)
        return (base + FOLLOWUP_NOTE) if history else base

    def prompt(self, question: str, hits: Iterable[Hit],
               history: Iterable[Turn] | None = None) -> str:
        return self.earlier(history) + self.context(hits) + "\n\nQuestion: " + question

    @staticmethod
    def named_last(question: str, hits: list[Hit]) -> list[Hit]:
        """Put the entries the question names by name at the end of the excerpts.

        Asked "What level is Gurglegut?" with Gurglegut as excerpt [1] of eight,
        the 4B answered that no such creature exists -- consistently, with the
        excerpt's header saying "Gurglegut (creature, level 12)". Moved to
        excerpt [8], next to the question, it answered "level 12" every time;
        a sentence pointing at [1] changed nothing. Small models read the end
        of a long context better than its start, so the entry the question is
        plainly about goes last. Only names of four characters or more, matched
        verbatim; everything else keeps its retrieval order.
        """
        q = question.lower()
        named = [h for h in hits if len(h.name or "") >= 4 and h.name.lower() in q]
        if not named:
            return hits
        return [h for h in hits if h not in named] + named

    def ask(self, question: str, k: int = DEFAULT_K, rerank: bool = True,
            pool: int | None = None, expand: int = DEFAULT_EXPAND,
            max_tokens: int | None = None, scope: str = DEFAULT_SCOPE,
            history: Iterable[Turn] | None = None) -> dict:
        max_tokens = self.answer_tokens if max_tokens is None else max_tokens
        plan, hits, timings = self.retrieve(question, k=k, rerank=rerank,
                                            pool=pool, expand=expand, scope=scope,
                                            history=history)
        # The condensed question is the one that names things, so it is the one
        # `named_last` can match; the question the model answers is still the
        # one that was typed.
        hits = self.named_last(plan.get("standalone") or question, hits)
        t = time.time()
        answer = self.ollama.chat(self.answer_system(history, hits),
                                  self.prompt(question, hits, history),
                                  self.manifest["ollama_llm"], max_tokens=max_tokens)
        timings["answer"] = round(time.time() - t, 2)
        timings["total"] = round(sum(timings.values()), 2)
        return {"question": question, "answer": answer, "plan": plan,
                "scope": "lore" if plan.get("lore") else "rules",
                "timings": timings, "hits": hits,
                "sources": [{"name": h.name, "category": h.category, "url": h.url,
                             "corpus": h.corpus} for h in hits]}

    _MENTION_KINDS = ("action", "feat", "spell", "condition", "skill", "equipment", "weapon",
                      "armor", "class-feature", "archetype", "trait", "rules")

    def mentions(self, text: str, exclude: set[str] | None = None, limit: int = 12) -> list[Hit]:
        """Index entries whose names appear in ``text``, as Hits the page can open.

        The answer says "You can Grab an Edge as a reaction"; the reader wants
        to click that. Names are matched as word n-grams, one to five words,
        against the current (non-legacy) entries of the kinds a rule refers
        to. Names under four characters are skipped: "Aid" and "Hide" match too
        much prose to be worth a wrong link.
        """
        names = self._name_table()
        # URLs are not prose: "…/Feats.aspx" is not a mention of the Feats page.
        words = re.findall(r"[A-Za-z][A-Za-z'’\-]*", re.sub(r"https?://\S+", " ", text))
        found: dict[str, int] = {}
        for n in range(5, 0, -1):
            for i in range(len(words) - n + 1):
                span = words[i:i + n]
                key = " ".join(span).lower()
                pos = names.get(key)
                if pos is None or key in found:
                    continue
                # A short name that is also an ordinary word ("Damage", "Eliminate")
                # links only when the prose writes it as a name, capitalised.
                # Conditions are the exception: rules text says "prone".
                meta = self.index.meta[pos]
                cat = meta.get("category")
                capitalised = all(w[0].isupper() for w in span)
                if n <= 2 and cat == "rules" and not capitalised:
                    continue
                if n == 1 and cat != "condition" and not capitalised:
                    continue
                # The wiki has a page for almost any capitalised word ("Following",
                # "Magic"). A one-word lore name links only where the prose uses
                # it mid-sentence, where the capital is the name's and not the
                # sentence's.
                if n == 1 and meta.get("corpus") == "pathfinderwiki" and not re.search(
                        r"(?<![.!?:]\s)(?<!\n)\b" + re.escape(span[0]) + r"\b", text[1:]):
                    continue
                found[key] = pos
        hits = []
        for key, pos in found.items():
            m = self.index.meta[pos]
            if exclude and m.get("url") in exclude:
                continue
            hits.append(self._hit(pos))
            if len(hits) >= limit:
                break
        return hits

    def _name_table(self) -> dict[str, int]:
        table = getattr(self, "_names", None)
        if table is None:
            table = {}
            for pos, m in enumerate(self.index.meta):
                name = (m.get("name") or "").strip()
                # Lore: whole articles only ("Cheliax", not "Cheliax › History"),
                # of every kind -- a person or a nation named in an answer is as
                # worth a link as a feat. The rules rows come first in the file,
                # so on a shared name the Archives' entry keeps the link.
                lore = m.get("corpus") == "pathfinderwiki"
                if lore and "#" in (m.get("id") or ""):
                    continue
                if (len(name) < 4 or (not lore and m.get("category") not in self._MENTION_KINDS)
                        or m.get("remaster_status") == "legacy"):
                    continue
                key = " ".join(re.findall(r"[A-Za-z][A-Za-z'’\-]*", name)).lower()
                if key and len(key.split()) <= 5:
                    # Prefer the entry whose kind a rule most often means.
                    table.setdefault(key, pos)
            self._names = table
        return table

    def ask_stream(self, question: str, k: int = DEFAULT_K, rerank: bool = True,
                   pool: int | None = None, expand: int = DEFAULT_EXPAND,
                   max_tokens: int | None = None,
                   scope: str = DEFAULT_SCOPE,
                   history: Iterable[Turn] | None = None) -> Iterator[dict]:
        """Yield one `sources` event, then `token` events, then `done`."""
        max_tokens = self.answer_tokens if max_tokens is None else max_tokens
        plan, hits, timings = self.retrieve(question, k=k, rerank=rerank,
                                            pool=pool, expand=expand, scope=scope,
                                            history=history)
        hits = self.named_last(plan.get("standalone") or question, hits)
        # `hits` carries the Hit objects (full body text) for a caller that wants
        # to render cards; `sources` is the JSON-safe citation list.
        yield {"event": "sources", "plan": plan, "timings": dict(timings), "hits": hits,
               "scope": "lore" if plan.get("lore") else "rules",
               "sources": [{"name": h.name, "category": h.category, "url": h.url,
                            "corpus": h.corpus} for h in hits]}
        t = time.time()
        first = None
        pieces: list[str] = []
        for piece in self.ollama.stream(self.answer_system(history, hits),
                                        self.prompt(question, hits, history),
                                        self.manifest["ollama_llm"],
                                        max_tokens=max_tokens):
            if first is None:
                first = round(time.time() - t, 2)
                timings["first_token"] = first
            pieces.append(piece)
            yield {"event": "token", "text": piece}
        timings["answer"] = round(time.time() - t, 2)
        timings["total"] = round(sum(v for key, v in timings.items()
                                     if key != "first_token"), 2)
        yield {"event": "done", "timings": timings, "answer": "".join(pieces)}
