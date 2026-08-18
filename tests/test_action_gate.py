import pytest

from controlplane.action.gate import ActionGate
from controlplane.types import Actor, Decision, ProposedAction, Request


def make(name, value, perms, reversible=True):
    return Request(prompt="x",
                   actor=Actor("u", role="support_agent", permissions=perms),
                   proposed_action=ProposedAction(name, value_usd=value,
                                                  reversible=reversible))


class TestActionGate:
    def setup_method(self):
        self.gate = ActionGate()

    def test_unregistered_action_is_denied(self):
        """Fail closed: anything not in policy is blocked at the intent stage."""
        r = make("wire_transfer", 100, ["*"])
        res = self.gate.evaluate(r, r.proposed_action)
        assert res.decision is Decision.BLOCK and res.stage == "intent"

    def test_missing_permission_blocks(self):
        r = make("issue_refund", 50, [])
        res = self.gate.evaluate(r, r.proposed_action)
        assert res.decision is Decision.BLOCK and res.stage == "permission"

    def test_above_hard_limit_blocks(self):
        r = make("issue_refund", 9000, ["refunds.write"])
        res = self.gate.evaluate(r, r.proposed_action)
        assert res.decision is Decision.BLOCK and res.stage == "risk"

    def test_above_auto_approve_holds_for_human(self):
        r = make("issue_refund", 4800, ["refunds.write"])
        res = self.gate.evaluate(r, r.proposed_action)
        assert res.decision is Decision.HOLD and res.stage == "policy"

    def test_small_permitted_action_executes(self):
        r = make("issue_refund", 50, ["refunds.write"])
        res = self.gate.evaluate(r, r.proposed_action)
        assert res.allowed and res.stage == "execute"

    def test_no_action_always_passes(self):
        r = Request(prompt="x", actor=Actor("u"))
        assert self.gate.evaluate(r, None).allowed

    def test_executor_missing_raises(self):
        with pytest.raises(KeyError):
            self.gate.execute(ProposedAction("issue_refund", {}))
