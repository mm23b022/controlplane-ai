"""Privacy / DLP scanner.

Detection is separate from decision: this module reports WHAT was found and
WHERE it is going. Whether that is a violation is decided by the policy engine,
because the same account number is fine internally and a breach externally.
"""
from __future__ import annotations

import re

PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(r"\b[\w\.\-\+]+@[\w\-]+\.[A-Za-z]{2,}\b"),
    "phone": re.compile(r"\b(?:\+?\d{1,3}[\s\-])?(?:\d{3,5}[\s\-]){1,2}\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ \-]?){13,16}\b"),
    "account_number": re.compile(r"\b\d{4}[\-\s]\d{4}[\-\s]\d{4}\b"),
    "government_id": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "api_key": re.compile(r"\b(?:sk|pk|api|key)[-_][A-Za-z0-9]{16,}\b", re.IGNORECASE),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
    # TODO[FILL]: add region-specific identifiers your organisation handles,
    # e.g. Aadhaar, PAN, NHS number, IBAN, policy numbers.
}

# Order matters: the most specific pattern should win when spans overlap.
_PRIORITY = ["private_key", "api_key", "government_id", "account_number",
             "credit_card", "email", "phone"]


def scan(text: str) -> list[dict]:
    """Return [{class, value, span}] with overlapping matches de-duplicated."""
    hits: list[dict] = []
    claimed: list[tuple[int, int]] = []

    for cls in _PRIORITY:
        pattern = PATTERNS.get(cls)
        if not pattern:
            continue
        for m in pattern.finditer(text):
            span = m.span()
            if any(span[0] < c[1] and c[0] < span[1] for c in claimed):
                continue
            claimed.append(span)
            hits.append({"class": cls, "value": m.group(0), "span": span})
    return hits


def redact(text: str, hits: list[dict]) -> str:
    """Deterministic EDIT: mask the value in place, leaving the rest intact."""
    out = text
    for hit in sorted(hits, key=lambda h: h["span"][0], reverse=True):
        start, end = hit["span"]
        out = out[:start] + f"[REDACTED:{hit['class'].upper()}]" + out[end:]
    return out
