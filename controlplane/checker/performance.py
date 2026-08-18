"""PERFORMANCE -- "Is it right?"

Verification ladder, cheapest rung first:
    calculator -> schema -> evidence/database -> self-check -> verifier -> human
The ladder stops as soon as the answer is settled (EARLY EXIT).
"""
from __future__ import annotations

import time

from controlplane.checker.detectors import deterministic
from controlplane.checker.detectors.claims import extract_claims, ground
from controlplane.evidence.store import EvidenceStore, default_store
from controlplane.types import (CheckResult, Decision, Dimension, Finding,
                                Generation, Request, RiskClass, Severity, TaskProfile)

_HEDGES = ("i think", "probably", "i believe", "should be", "might be", "not sure",
           "could not verify", "as far as i know")
_CONFIDENT = ("confirmed", "certainly", "definitely", "guaranteed", "verified",
              "without doubt", "exactly")


class PerformanceChecker:
    def __init__(self, store: EvidenceStore | None = None,
                 verifier: "LLMVerifier | None" = None) -> None:
        self.store = store or default_store
        self.verifier = verifier or LLMVerifier()

    def check(self, request: Request, generation: Generation,
              profile: TaskProfile) -> CheckResult:
        started = time.time()
        result = CheckResult(dimension=Dimension.PERFORMANCE)

        # --- Rung 1: calculator (deterministic, always cheap) -----------------
        result.checks_run.append("calculator")
        result.findings += deterministic.check_arithmetic(generation.text)

        required = request.metadata.get("required_fields")
        if required:
            result.checks_run.append("schema")
            result.findings += deterministic.check_schema(generation.text, required)

        # EARLY EXIT: a deterministic proof needs no model to confirm it.
        if any(f.decisive for f in result.findings):
            result.early_exit = True
            result.latency_ms = int((time.time() - started) * 1000)
            return result

        # --- Rung 2: evidence grounding (Class B and above) -------------------
        if profile.risk_class in (RiskClass.B, RiskClass.C) or profile.is_factual:
            result.checks_run.append("evidence")
            verdicts = ground(extract_claims(generation.text), self.store)
            contradicted = [v for v in verdicts if v.status == "CONTRADICTED"]
            uncertain = [v for v in verdicts if v.status == "UNCERTAIN"
                         and v.claim.checkable]

            for v in contradicted:
                result.findings.append(Finding(
                    dimension=Dimension.PERFORMANCE,
                    category="contradicted_by_source",
                    severity=Severity.CRITICAL,
                    confidence=0.95,
                    message=f"Claim conflicts with the system of record: {v.detail}.",
                    evidence=(v.passage.text[:160] if v.passage else None),
                    deterministic=bool(v.passage and v.passage.authoritative),
                    recommended=Decision.REGENERATE,
                    fixable=True,
                ))
            for v in uncertain:
                result.findings.append(Finding(
                    dimension=Dimension.PERFORMANCE,
                    category="unsupported_claim",
                    severity=Severity.LOW,
                    confidence=0.6,
                    message=f"Claim could not be grounded: {v.claim.text[:90]}",
                    deterministic=False,
                    recommended=Decision.ANNOTATE,
                ))

            if any(f.decisive for f in result.findings):
                result.early_exit = True
                result.latency_ms = int((time.time() - started) * 1000)
                return result

        # --- Rung 3: confidence calibration ----------------------------------
        result.checks_run.append("calibration")
        result.findings += self._calibration(generation.text, result)

        # --- Rung 4: independent verifier (Class C, or unresolved doubt) ------
        needs_verifier = profile.risk_class is RiskClass.C or any(
            f.severity.rank >= Severity.MEDIUM.rank for f in result.findings)
        if needs_verifier and self.verifier.available:
            result.checks_run.append("llm_verifier")
            vf, cost = self.verifier.verify(request, generation)
            result.findings += vf
            result.cost_usd += cost

        result.latency_ms = int((time.time() - started) * 1000)
        return result

    @staticmethod
    def _calibration(text: str, result: CheckResult) -> list[Finding]:
        low = text.lower()
        confident = any(c in low for c in _CONFIDENT)
        hedged = any(h in low for h in _HEDGES)
        weak_evidence = any(f.category == "unsupported_claim" for f in result.findings)

        out: list[Finding] = []
        if confident and weak_evidence:
            out.append(Finding(
                dimension=Dimension.PERFORMANCE,
                category="overconfident",
                severity=Severity.MEDIUM,
                confidence=0.7,
                message="Confident phrasing on claims that evidence does not support.",
                recommended=Decision.ANNOTATE,
                fixable=True,
            ))
        if hedged:
            out.append(Finding(
                dimension=Dimension.PERFORMANCE,
                category="low_confidence_answer",
                severity=Severity.LOW,
                confidence=0.8,
                message="Model hedged; answer may be incomplete.",
                recommended=Decision.ANNOTATE,
            ))
        return out


class LLMVerifier:
    """Rung 5: an independent model judges the answer.

    TODO[FILL] -- deliberately unimplemented.

    Set `available = True` and implement `verify()` to call a *different* model
    from the generator (self-check is cheap but is not independent proof).
    Return structured findings, never free text:

        prompt = VERIFIER_TEMPLATE.format(question=request.prompt,
                                          answer=generation.text)
        raw = provider.complete(...)         # a small, cheap model is fine
        data = json.loads(raw.text)          # {verdict, category, severity, reason}
        return [Finding(dimension=Dimension.PERFORMANCE, ...)], raw.cost_usd

    Remember: the verifier is a DETECTOR, not the final authority. The Decision
    Engine still decides what happens.
    """

    available: bool = False

    def verify(self, request: Request, generation: Generation
               ) -> tuple[list[Finding], float]:
        raise NotImplementedError(
            "LLMVerifier.verify() is a deliberate gap - see the docstring."
        )
