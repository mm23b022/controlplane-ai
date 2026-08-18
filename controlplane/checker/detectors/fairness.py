"""Fairness / bias detection.

Two layers:
  1. Stereotype detection on the text itself  -- implemented below.
  2. Comparative fairness across equivalent cases -- TODO[FILL].

Layer 2 is deliberately unimplemented because it cannot be done from text alone:
it needs your historical decision data to compare how similar candidates,
applicants or customers were actually treated.
"""
from __future__ import annotations

import re

from config.settings import policies
from controlplane.types import Decision, Dimension, Finding, Severity

_STEREOTYPE = re.compile(
    r"\b(?:women|men|males?|females?|elderly|older|younger|immigrants?|"
    r"foreigners?)\b[^.?!]{0,60}\b(?:generally|typically|usually|tend to|are less|"
    r"are more|always|never|struggle|cannot|can't)\b",
    re.IGNORECASE,
)


def scan(text: str, context: str = "") -> list[Finding]:
    cfg = policies().get("fairness", {})
    high_impact = any(c in (context or "").lower()
                      for c in cfg.get("high_impact_contexts", []))
    findings: list[Finding] = []

    m = _STEREOTYPE.search(text)
    if m:
        findings.append(Finding(
            dimension=Dimension.RESPONSIBILITY,
            category="stereotype",
            severity=Severity.CRITICAL if high_impact else Severity.HIGH,
            confidence=0.85,
            message="Generalisation about a protected group used as a reason.",
            evidence=m.group(0)[:160],
            deterministic=False,
            recommended=Decision.BLOCK if high_impact else Decision.REGENERATE,
            fixable=not high_impact,
        ))

    low = text.lower()
    mentioned = [a for a in cfg.get("protected_attributes", []) if a in low]
    proxies = [p for p in cfg.get("proxy_attributes", []) if p in low]
    if high_impact and (mentioned or proxies):
        findings.append(Finding(
            dimension=Dimension.RESPONSIBILITY,
            category="protected_attribute_in_decision",
            severity=Severity.HIGH,
            confidence=0.7,
            message=(f"High-impact decision references "
                     f"{', '.join(mentioned + proxies)}; needs fairness review."),
            deterministic=False,
            recommended=Decision.HOLD,
        ))
    return findings


def comparative_fairness(subject: dict, cohort: list[dict]) -> list[Finding]:
    """Compare this decision against outcomes for equivalent cases.

    TODO[FILL]: implement against your historical decisions store.
    Suggested approach:
      1. Select cohort members whose non-protected features match `subject`.
      2. Compute outcome rate for each protected group in that cohort.
      3. Flag when the disparity exceeds your fairness threshold
         (e.g. four-fifths rule: min_rate / max_rate < 0.8).
    Return a HIGH-severity Finding recommending HOLD when the rule is breached.
    """
    return []
