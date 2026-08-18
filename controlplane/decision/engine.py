"""DECISION ENGINE -- turns risk + evidence + consequence into ONE action.

Detection is deliberately separate from decision. The same finding produces a
different action depending on consequence, destination and reversibility.

Matrix (from the control strategy):
    low risk    + strong support   -> ALLOW
    low risk    + uncertain        -> ANNOTATE
    medium risk + fixable          -> REGENERATE
    high risk   + verified breach  -> BLOCK
    high risk   + unresolved doubt -> HOLD
"""
from __future__ import annotations

from controlplane.checker.detectors import pii
from controlplane.types import (CheckResult, ControlDecision, Decision, Dimension,
                                Finding, Request, RiskClass, Severity, TaskProfile)

_ORDER = [Decision.ALLOW, Decision.ANNOTATE, Decision.REGENERATE,
          Decision.HOLD, Decision.BLOCK]


def _stricter(a: Decision, b: Decision) -> Decision:
    return a if _ORDER.index(a) >= _ORDER.index(b) else b


class DecisionEngine:
    def __init__(self, max_attempts: int = 2) -> None:
        self.max_attempts = max_attempts

    def decide(self, request: Request, profile: TaskProfile,
               results: list[CheckResult], attempt: int = 1) -> ControlDecision:
        findings: list[Finding] = [f for r in results for f in r.findings]
        if not findings:
            return ControlDecision(Decision.ALLOW, "No material findings.", [])

        high_consequence = (
            profile.risk_class is RiskClass.C
            or (request.proposed_action is not None
                and not request.proposed_action.reversible)
            or request.destination.external
        )

        decision = Decision.ALLOW
        reasons: list[str] = []
        annotations: list[str] = []

        for f in findings:
            proposed = self._for_finding(f, high_consequence, attempt)
            if proposed is Decision.ANNOTATE:
                annotations.append(f.message)
            if _ORDER.index(proposed) > _ORDER.index(decision):
                reasons = [f"{f.category}: {f.message}"]
            elif proposed is decision and proposed is not Decision.ALLOW:
                reasons.append(f"{f.category}: {f.message}")
            decision = _stricter(decision, proposed)

        # A regeneration that has already been retried becomes a human decision.
        if decision is Decision.REGENERATE and attempt > self.max_attempts:
            decision = Decision.HOLD
            reasons.insert(0, f"still failing after {attempt - 1} regeneration(s)")

        return ControlDecision(
            decision=decision,
            reason="; ".join(reasons[:3]) or "No material findings.",
            findings=findings,
            annotations=annotations,
            requires_human=decision is Decision.HOLD,
        )

    # ------------------------------------------------------------------
    def _for_finding(self, f: Finding, high_consequence: bool, attempt: int) -> Decision:
        # Cost findings never gate an answer; they are observations.
        if f.dimension is Dimension.COST and f.severity.rank < Severity.HIGH.rank:
            return Decision.ALLOW

        # A proven, severe violation is decisive -- no further deliberation.
        if f.decisive:
            return f.recommended or Decision.BLOCK

        if f.severity is Severity.CRITICAL:
            # Proven -> block. Inferred -> a human decides.
            return Decision.BLOCK if f.confidence >= 0.9 else Decision.HOLD

        if f.severity is Severity.HIGH:
            if high_consequence:
                return Decision.HOLD
            return Decision.REGENERATE if f.fixable else Decision.HOLD

        if f.severity is Severity.MEDIUM:
            if f.fixable and attempt <= self.max_attempts:
                return Decision.REGENERATE
            return Decision.HOLD if high_consequence else Decision.ANNOTATE

        if f.severity is Severity.LOW:
            return Decision.ANNOTATE

        return Decision.ALLOW


def apply_deterministic_edits(text: str, findings: list[Finding]) -> tuple[str, list[str]]:
    """EDIT, NEVER REWRITE.

    An edit is applied only when the correction is deterministic -- masking an
    identifier, dropping a prohibited field. A broken reasoning chain is never
    patched to look safe; that is what REGENERATE is for.
    """
    applied: list[str] = []
    out = text
    redact_classes = {
        f.deterministic_fix.split(":", 1)[1]
        for f in findings
        if f.deterministic_fix and f.deterministic_fix.startswith("redact:")
    }
    if redact_classes:
        hits = [h for h in pii.scan(out) if h["class"] in redact_classes]
        if hits:
            out = pii.redact(out, hits)
            applied.append(f"masked {len(hits)} identifier(s): "
                           f"{', '.join(sorted(redact_classes))}")
    return out, applied
