"""The runtime: a Pathfinder 2e rules assistant that runs on a laptop.

Everything heavy is delegated to Ollama over HTTP, so this package needs only
numpy, httpx and orjson -- no torch, no transformers, no CUDA. On a 16 GB
MacBook the resident cost is the two models Ollama holds (about 6.3 GB) plus
roughly 250 MB of memory-mapped index.

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

INDEX_URL = ("https://github.com/DeastinY/pf2etune/releases/download/"
             "index-v1/pf2e-index.tar.gz")


def default_index() -> pathlib.Path:
    """Where the index lives, whether this is a clone or an installed tool.

    Running from a checkout, ``dist/pf2e-index`` is right there. Installed with
    ``uv tool install`` or run with ``uvx``, the package sits in a cache that is
    wiped on upgrade, so a 244 MB index cannot live beside it -- it goes to the
    user data directory instead and survives.
    """
    repo = pathlib.Path(__file__).resolve().parents[2] / "dist" / "pf2e-index"
    if (repo / "manifest.json").exists():
        return repo
    env = os.environ.get("PF2E_INDEX")
    if env:
        return pathlib.Path(env).expanduser()
    if sys.platform == "darwin":
        base = pathlib.Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = pathlib.Path(os.environ.get("LOCALAPPDATA", pathlib.Path.home()))
    else:
        base = pathlib.Path(os.environ.get("XDG_DATA_HOME",
                                           pathlib.Path.home() / ".local" / "share"))
    return base / "pf2etune" / "pf2e-index"


DEFAULT_INDEX = default_index()

CATEGORIES = ("action", "condition", "feat", "spell", "equipment", "weapon", "armor",
              "creature", "hazard", "trait", "rules", "class-feature", "ritual",
              "archetype", "background", "heritage", "deity", "shield")

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

RE_CLEAN = re.compile(r"^[\s\-*\d.)]+|[\s;:]+$")

# The TREC default of 60 flattens rank differences almost to nothing when fusing a
# handful of 50-item rankings: rank 1 scores 0.0164 and rank 10 scores 0.0143.
# Swept on the holdout; 5 was best, though the margin is inside the noise of a
# 48-item sample.
RRF_SMOOTHING = 5

# Characters of each retrieved entry put in front of the model. Swept on the
# holdout; see notes/experiments.md.
CONTEXT_CHARS = 1600

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
                f"Fetch it with:  pf2e setup\n"
                f"or point --index at an unpacked pf2e-index directory."
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
        self._base_mask = self.index.allowed(exclude_legacy=False)

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

        The index is 250 MB of memory-mapped arrays, a BM25 matrix and 41,743
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

    def rewrite(self, question: str) -> dict:
        try:
            raw = self.ollama.chat(REWRITE_SYSTEM, f"Question: {question}",
                                   self.manifest["ollama_llm"], max_tokens=90)
        except OllamaError:
            raise
        except Exception:
            return {"summary": "", "categories": []}
        summary, kinds = "", []
        for line in raw.splitlines():
            line = line.strip()
            if line.upper().startswith("SUMMARY:"):
                summary = RE_CLEAN.sub("", line.split(":", 1)[1]).strip()
            elif line.upper().startswith("KINDS:"):
                for part in line.split(":", 1)[1].split(","):
                    part = part.strip().lower().replace(" ", "-")
                    if part in CATEGORIES and part not in kinds:
                        kinds.append(part)
        return {"summary": summary[:220], "categories": kinds[:3]}

    def _embed_queries(self, texts: list[str]) -> np.ndarray:
        prefix = self.manifest["query_prefix"]
        return self.embed_client.embed([prefix + t for t in texts],
                                       self.manifest["ollama_embed"])

    def search(self, question: str, k: int = DEFAULT_K, plan: dict | None = None,
               rerank: bool = True, pool: int | None = None,
               expand: int = DEFAULT_EXPAND) -> list[Hit]:
        plan = plan if plan is not None else self.rewrite(question)
        queries = [question]
        if plan.get("summary"):
            queries.append(plan["summary"])
        vecs = self._embed_queries(queries).astype(np.float32)
        qvec, hvec = vecs[0], (vecs[1] if len(vecs) > 1 else None)

        mask = self._base_mask
        # Narrowing to the rewriter's entry kinds sharpens entity lookup and blinds
        # concept questions -- the rules chapters are excluded, and that is where
        # "is a critical failure a failure?" is answered. So both rankings are
        # kept and fused rather than one replacing the other. Costs one extra
        # scan of a memory-mapped matrix and no model call.
        narrow_mask = None
        if plan.get("categories"):
            narrowed = mask & self.index.allowed(exclude_legacy=False,
                                                 categories=plan["categories"])
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

        hits = []
        for i in order:
            m = self.index.meta[i]
            hits.append(Hit(chunk_id=self.index.ids[i], name=m.get("name") or "",
                            category=m.get("category") or "", level=m.get("level"),
                            url=m.get("url") or "", text=self.body(self.index.ids[i]),
                            summary=m.get("summary") or ""))
        if rerank:
            hits = self.rerank(question, hits, k)
        return hits

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
            f"{n}. {h.name} ({h.category.replace('-', ' ')})"
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
        blocks = []
        for n, h in enumerate(hits, 1):
            head = f"[{n}] {h.name} ({h.category.replace('-', ' ')}"
            if h.level is not None:
                head += f", level {h.level}"
            head += f") — {h.url}"
            blocks.append(head + "\n" + h.text[:max_chars].strip())
        return "<rules_excerpts>\n" + "\n\n".join(blocks) + "\n</rules_excerpts>"

    def retrieve(self, question: str, k: int = DEFAULT_K, rerank: bool = True,
                 pool: int | None = None, expand: int = DEFAULT_EXPAND) -> tuple:
        """Everything up to the answer call, timed per stage.

        Split out from `ask` so the web UI can put sources on screen while the
        answer is still decoding, and so no caller has to run retrieval twice to
        get both halves of a result.
        """
        timings: dict[str, float] = {}
        t = time.time()
        plan = self.rewrite(question)
        timings["rewrite"] = round(time.time() - t, 2)

        t = time.time()
        hits = self.search(question, k=k, plan=plan, rerank=False,
                           pool=pool or DEFAULT_POOL, expand=expand)
        timings["retrieve"] = round(time.time() - t, 2)

        if rerank:
            t = time.time()
            hits = self.rerank(question, hits, k)
            timings["rerank"] = round(time.time() - t, 2)
        return plan, hits[:k], timings

    def prompt(self, question: str, hits: Iterable[Hit]) -> str:
        return self.context(hits) + "\n\nQuestion: " + question

    def ask(self, question: str, k: int = DEFAULT_K, rerank: bool = True,
            pool: int | None = None, expand: int = DEFAULT_EXPAND,
            max_tokens: int | None = None) -> dict:
        max_tokens = self.answer_tokens if max_tokens is None else max_tokens
        plan, hits, timings = self.retrieve(question, k=k, rerank=rerank,
                                            pool=pool, expand=expand)
        t = time.time()
        answer = self.ollama.chat(ANSWER_SYSTEM, self.prompt(question, hits),
                                  self.manifest["ollama_llm"], max_tokens=max_tokens)
        timings["answer"] = round(time.time() - t, 2)
        timings["total"] = round(sum(timings.values()), 2)
        return {"question": question, "answer": answer, "plan": plan,
                "timings": timings, "hits": hits,
                "sources": [{"name": h.name, "category": h.category, "url": h.url}
                            for h in hits]}

    def ask_stream(self, question: str, k: int = DEFAULT_K, rerank: bool = True,
                   pool: int | None = None, expand: int = DEFAULT_EXPAND,
                   max_tokens: int | None = None) -> Iterator[dict]:
        """Yield one `sources` event, then `token` events, then `done`."""
        max_tokens = self.answer_tokens if max_tokens is None else max_tokens
        plan, hits, timings = self.retrieve(question, k=k, rerank=rerank,
                                            pool=pool, expand=expand)
        # `hits` carries the Hit objects (full body text) for a caller that wants
        # to render cards; `sources` is the JSON-safe citation list.
        yield {"event": "sources", "plan": plan, "timings": dict(timings), "hits": hits,
               "sources": [{"name": h.name, "category": h.category, "url": h.url}
                           for h in hits]}
        t = time.time()
        first = None
        for piece in self.ollama.stream(ANSWER_SYSTEM, self.prompt(question, hits),
                                        self.manifest["ollama_llm"],
                                        max_tokens=max_tokens):
            if first is None:
                first = round(time.time() - t, 2)
                timings["first_token"] = first
            yield {"event": "token", "text": piece}
        timings["answer"] = round(time.time() - t, 2)
        timings["total"] = round(sum(v for key, v in timings.items()
                                     if key != "first_token"), 2)
        yield {"event": "done", "timings": timings}
