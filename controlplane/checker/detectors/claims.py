"""Claim extraction and evidence grounding.

Claim-level, not answer-level: one weak sentence should not condemn an entire
response, and one strong sentence should not launder a weak one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from controlplane.evidence.store import EvidenceStore, Passage

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_NUMBER = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")


@dataclass
class Claim:
    text: str
    numbers: list[str]
    checkable: bool


@dataclass
class ClaimVerdict:
    claim: Claim
    status: str                  # SUPPORTED | CONTRADICTED | UNCERTAIN
    passage: Passage | None = None
    detail: str = ""


def extract_claims(text: str) -> list[Claim]:
    claims = []
    for sentence in _SENTENCE.split(text.strip()):
        s = sentence.strip()
        if len(s) < 12:
            continue
        numbers = _NUMBER.findall(s)
        claims.append(Claim(text=s, numbers=numbers, checkable=bool(numbers)))
    return claims


def _norm(n: str) -> str:
    return n.replace("$", "").replace(",", "").rstrip(".").rstrip("0").rstrip(".")


def ground(claims: list[Claim], store: EvidenceStore,
           k: int = 3) -> list[ClaimVerdict]:
    """Compare each numeric claim against retrieved evidence.

    A number that appears in an authoritative passage is SUPPORTED. A number
    that conflicts with a number of the same kind in that passage is
    CONTRADICTED. Anything unretrievable is UNCERTAIN, never silently accepted.
    """
    verdicts: list[ClaimVerdict] = []
    for claim in claims:
        if not claim.checkable:
            verdicts.append(ClaimVerdict(claim, "UNCERTAIN", None, "no checkable value"))
            continue

        passages = store.retrieve(claim.text, k=k)
        if not passages:
            verdicts.append(ClaimVerdict(claim, "UNCERTAIN", None, "no evidence retrieved"))
            continue

        best = passages[0]
        evidence_numbers = {_norm(n) for n in _NUMBER.findall(best.text)}
        claim_numbers = {_norm(n) for n in claim.numbers}

        if claim_numbers & evidence_numbers:
            verdicts.append(ClaimVerdict(claim, "SUPPORTED", best, "value matches source"))
        elif evidence_numbers:
            verdicts.append(ClaimVerdict(
                claim, "CONTRADICTED", best,
                f"stated {sorted(claim_numbers)}, source has {sorted(evidence_numbers)}"))
        else:
            verdicts.append(ClaimVerdict(claim, "UNCERTAIN", best, "source has no comparable value"))
    return verdicts
