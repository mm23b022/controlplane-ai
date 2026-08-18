"""Prompt-injection detection.

Principle from the strategy: model output must never be able to rewrite
ControlPlane's own control policy. We look for attempts in retrieved context
and in the generated text itself.
"""
from __future__ import annotations

import re

from controlplane.types import Decision, Dimension, Finding, Severity

_SIGNATURES = [
    r"ignore (?:all |any )?(?:previous|prior|above) instructions",
    r"disregard (?:the )?(?:system|previous) (?:prompt|instructions)",
    r"you are now (?:in )?(?:developer|admin|god) mode",
    r"reveal (?:your |the )?(?:system prompt|instructions)",
    r"(?:disable|bypass|skip) (?:the )?(?:safety|guardrail|control|audit|checker)",
    r"do not (?:log|record|audit) this",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _SIGNATURES]


def scan(text: str, source: str = "output") -> list[Finding]:
    findings = []
    for pattern in _COMPILED:
        m = pattern.search(text)
        if m:
            findings.append(Finding(
                dimension=Dimension.RESPONSIBILITY,
                category="prompt_injection",
                severity=Severity.CRITICAL,
                confidence=0.95,
                message=f"Instruction-override attempt detected in {source}.",
                evidence=m.group(0)[:160],
                deterministic=True,
                recommended=Decision.BLOCK,
            ))
    return findings
