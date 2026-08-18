from controlplane.decision.engine import DecisionEngine, apply_deterministic_edits
from controlplane.types import (Actor, CheckResult, Decision, Destination, Dimension,
                                Finding, ProposedAction, Request, RiskClass, Severity,
                                TaskProfile, TaskType)


def profile(risk=RiskClass.A):
    return TaskProfile(TaskType.CONVERSATION, 0.2, False, risk_class=risk)


def result(*findings):
    return [CheckResult(Dimension.PERFORMANCE, list(findings))]


def finding(**kw):
    base = dict(dimension=Dimension.PERFORMANCE, category="x",
                severity=Severity.LOW, confidence=0.9, message="m")
    base.update(kw)
    return Finding(**base)


class TestDecisionMatrix:
    def setup_method(self):
        self.engine = DecisionEngine()
        self.req = Request(prompt="x", actor=Actor("u"))

    def test_no_findings_allows(self):
        d = self.engine.decide(self.req, profile(), [CheckResult(Dimension.PERFORMANCE)])
        assert d.decision is Decision.ALLOW

    def test_low_severity_annotates(self):
        d = self.engine.decide(self.req, profile(), result(finding(severity=Severity.LOW)))
        assert d.decision is Decision.ANNOTATE and d.annotations

    def test_medium_fixable_regenerates(self):
        d = self.engine.decide(self.req, profile(),
                               result(finding(severity=Severity.MEDIUM, fixable=True)))
        assert d.decision is Decision.REGENERATE

    def test_proven_critical_blocks(self):
        d = self.engine.decide(self.req, profile(), result(finding(
            severity=Severity.CRITICAL, deterministic=True, confidence=1.0,
            recommended=Decision.BLOCK)))
        assert d.decision is Decision.BLOCK

    def test_uncertain_critical_holds_for_human(self):
        """Inferred, not proven -> a person decides rather than an automatic block."""
        d = self.engine.decide(self.req, profile(), result(finding(
            severity=Severity.CRITICAL, deterministic=False, confidence=0.6)))
        assert d.decision is Decision.HOLD

    def test_cost_findings_never_gate_the_answer(self):
        d = self.engine.decide(self.req, profile(), [CheckResult(
            Dimension.COST, [finding(dimension=Dimension.COST,
                                     severity=Severity.MEDIUM, category="over_budget")])])
        assert d.decision is Decision.ALLOW

    def test_high_consequence_escalates_to_hold(self):
        """The same finding is stricter when the action is irreversible."""
        f = finding(severity=Severity.MEDIUM, fixable=True)
        low = self.engine.decide(self.req, profile(), result(f))
        req_hi = Request(prompt="x", actor=Actor("u"),
                         proposed_action=ProposedAction("a", reversible=False))
        hi = self.engine.decide(req_hi, profile(RiskClass.C), result(f), attempt=9)
        assert low.decision is Decision.REGENERATE and hi.decision is Decision.HOLD

    def test_strictest_finding_wins(self):
        d = self.engine.decide(self.req, profile(), result(
            finding(severity=Severity.LOW),
            finding(severity=Severity.CRITICAL, deterministic=True, confidence=1.0,
                    recommended=Decision.BLOCK)))
        assert d.decision is Decision.BLOCK

    def test_low_risk_degrades_gracefully_after_retries(self):
        """Low-consequence traffic must never be blocked just because a fix
        failed: annotate the caveat and let the answer through."""
        d = self.engine.decide(self.req, profile(),
                               result(finding(severity=Severity.MEDIUM, fixable=True)),
                               attempt=5)
        assert d.decision is Decision.ANNOTATE

    def test_unfixable_regeneration_escalates_to_human(self):
        """A REGENERATE that keeps failing becomes a human decision, not a loop."""
        engine = DecisionEngine(max_attempts=2)
        req = Request(prompt="x", actor=Actor("u"),
                      destination=Destination(external=True))
        d = engine.decide(req, profile(RiskClass.C),
                          result(finding(severity=Severity.HIGH, fixable=True)),
                          attempt=3)
        assert d.decision is Decision.HOLD and d.requires_human


class TestDeterministicEdits:
    def test_masks_only_flagged_classes(self):
        text = "account 4488-1234-5678 and email a@b.com"
        f = finding(deterministic_fix="redact:account_number")
        out, applied = apply_deterministic_edits(text, [f])
        assert "4488-1234-5678" not in out
        assert "a@b.com" in out and applied

    def test_no_edits_without_deterministic_fix(self):
        text = "account 4488-1234-5678"
        out, applied = apply_deterministic_edits(text, [finding()])
        assert out == text and applied == []
