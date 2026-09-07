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

import pathlib
import re
from dataclasses import dataclass
from typing import Iterable

import httpx
import numpy as np
import orjson

from . import retrieval
from .bm25 import BM25

DEFAULT_INDEX = pathlib.Path(__file__).resolve().parents[2] / "dist" / "pf2e-index"
DEFAULT_OLLAMA = "http://localhost:11434"

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
    "and prefer them over your own recollection. Answer concisely and directly, and cite the "
    "source URL of any excerpt you use. If the excerpts do not contain the answer, say so plainly "
    "rather than guessing."
)

RE_CLEAN = re.compile(r"^[\s\-*\d.)]+|[\s;:]+$")

# The TREC default of 60 flattens rank differences almost to nothing when fusing a
# handful of 50-item rankings: rank 1 scores 0.0164 and rank 10 scores 0.0143.
# Swept on the holdout; 5 was best, though the margin is inside the noise of a
# 48-item sample.
RRF_SMOOTHING = 5

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


class Ollama:
    def __init__(self, base_url: str = DEFAULT_OLLAMA, timeout: float = 180.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

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

    def embed(self, texts: list[str], model: str) -> np.ndarray:
        data = self._post("/api/embed", {"model": model, "input": texts})
        vecs = np.asarray(data["embeddings"], dtype=np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / np.where(norms == 0, 1, norms)

    def chat(self, system: str, user: str, model: str, max_tokens: int = 700) -> str:
        data = self._post("/api/chat", {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "num_predict": max_tokens},
        })
        return (data.get("message") or {}).get("content", "").strip()


class Assistant:
    def __init__(self, index_dir: pathlib.Path = DEFAULT_INDEX,
                 ollama_url: str = DEFAULT_OLLAMA) -> None:
        index_dir = pathlib.Path(index_dir)
        if not (index_dir / "manifest.json").exists():
            raise OllamaError(
                f"No index at {index_dir}. Build one with scripts/package_index.py, "
                f"or point --index at an unpacked pf2e-index directory."
            )
        self.manifest = orjson.loads((index_dir / "manifest.json").read_bytes())
        self.ollama = Ollama(ollama_url)

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

    def body(self, chunk_id: str) -> str:
        span = self._body_offsets.get(chunk_id)
        if span is None:
            return ""
        offset, length = span
        with self._bodies_path.open("rb") as fh:
            fh.seek(offset)
            return orjson.loads(fh.read(length)).get("text", "")

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
        return self.ollama.embed([prefix + t for t in texts], self.manifest["ollama_embed"])

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
        take = (pool or DEFAULT_POOL) if rerank else k
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

    def context(self, hits: Iterable[Hit], max_chars: int = 1600) -> str:
        blocks = []
        for n, h in enumerate(hits, 1):
            head = f"[{n}] {h.name} ({h.category.replace('-', ' ')}"
            if h.level is not None:
                head += f", level {h.level}"
            head += f") — {h.url}"
            blocks.append(head + "\n" + h.text[:max_chars].strip())
        return "<rules_excerpts>\n" + "\n\n".join(blocks) + "\n</rules_excerpts>"

    def ask(self, question: str, k: int = DEFAULT_K, rerank: bool = True,
            pool: int | None = None, expand: int = DEFAULT_EXPAND) -> dict:
        plan = self.rewrite(question)
        hits = self.search(question, k=k, plan=plan, rerank=rerank, pool=pool, expand=expand)
        prompt = self.context(hits) + "\n\nQuestion: " + question
        answer = self.ollama.chat(ANSWER_SYSTEM, prompt, self.manifest["ollama_llm"])
        return {"question": question, "answer": answer, "plan": plan,
                "sources": [{"name": h.name, "category": h.category, "url": h.url} for h in hits]}
