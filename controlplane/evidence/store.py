"""CONTROLPLANE FOUNDATION -> evidence and knowledge.

EVIDENCE-FIRST: for factual claims, compare the claim against an authoritative
source *before* asking another model for an opinion. This is both cheaper and
avoids verifier hallucination.
"""
from __future__ import annotations

import abc
import re
from dataclasses import dataclass, field


@dataclass
class Passage:
    doc_id: str
    text: str
    score: float = 0.0
    source: str = "corpus"
    authoritative: bool = False   # True for systems of record (DB, ledger, API)


class EvidenceStore(abc.ABC):
    @abc.abstractmethod
    def retrieve(self, query: str, k: int = 5) -> list[Passage]: ...


_TOKEN = re.compile(r"[a-z0-9\.\-$,]+")
_STOP = {"the", "a", "an", "is", "of", "for", "to", "and", "in", "on", "what",
         "customer", "please", "this", "that", "it", "as"}


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


class InMemoryEvidenceStore(EvidenceStore):
    """A working keyword-overlap retriever. Good enough for grounding checks and
    for tests; swap for the vector store in production."""

    def __init__(self) -> None:
        self._docs: list[Passage] = []

    def add(self, doc_id: str, text: str, source: str = "corpus",
            authoritative: bool = False) -> None:
        self._docs.append(Passage(doc_id, text, source=source,
                                  authoritative=authoritative))

    def add_many(self, docs: list[tuple[str, str]]) -> None:
        for doc_id, text in docs:
            self.add(doc_id, text)

    def retrieve(self, query: str, k: int = 5) -> list[Passage]:
        q = set(_tokens(query))
        if not q:
            return []
        scored: list[Passage] = []
        for d in self._docs:
            dt = set(_tokens(d.text))
            overlap = len(q & dt)
            if not overlap:
                continue
            score = overlap / (len(q) ** 0.5 * max(1, len(dt)) ** 0.25)
            if d.authoritative:
                score *= 1.5
            scored.append(Passage(d.doc_id, d.text, round(score, 4),
                                  d.source, d.authoritative))
        return sorted(scored, key=lambda p: -p.score)[:k]


class VectorEvidenceStore(EvidenceStore):
    """TODO[FILL]: production retrieval backed by embeddings.

    Implement `retrieve` against your vector database (pgvector, Pinecone,
    Qdrant, Weaviate...). Keep the Passage contract identical and everything
    downstream -- grounding, citations, verification -- works unchanged.

        def retrieve(self, query, k=5):
            vec = embed(query)
            rows = self.client.search(vec, top_k=k)
            return [Passage(r.id, r.text, r.score, r.source, r.authoritative)
                    for r in rows]
    """

    def __init__(self, client=None) -> None:
        self.client = client

    def retrieve(self, query: str, k: int = 5) -> list[Passage]:
        raise NotImplementedError(
            "VectorEvidenceStore is a deliberate gap - see the docstring."
        )


default_store = InMemoryEvidenceStore()
