from controlplane.cai.router import CostIntelligenceAI
from controlplane.types import Actor, ProposedAction, Request, RiskClass


class TestRouting:
    def setup_method(self):
        self.cai = CostIntelligenceAI()

    def test_trivial_task_gets_cheap_model(self):
        r = Request(prompt="Say hello", actor=Actor("u"))
        assert self.cai.route(r).model_id == "mock-small"

    def test_hard_task_escalates(self):
        r = Request(prompt="Derive and prove the optimal pricing strategy, "
                           "evaluating every trade-off in detail " * 6,
                    actor=Actor("u"))
        d = self.cai.route(r)
        assert d.model_id in ("mock-mid", "mock-large")

    def test_never_recommends_below_success_floor(self):
        r = Request(prompt="Compare and evaluate these strategic options " * 8,
                    actor=Actor("u"))
        d = self.cai.route(r)
        assert d.expected_success >= 0.75

    def test_cheaper_than_best_when_possible(self):
        """The recommendable model should not always be the strongest one."""
        r = Request(prompt="Say hello", actor=Actor("u"))
        d = self.cai.route(r)
        assert d.model_id != d.best_model_id
        assert d.expected_cost_usd <= min(
            a["expected_cost_usd"] for a in d.alternatives
            if a["expected_success"] >= 0.8)

    def test_escalation_picks_stronger_model(self):
        r = Request(prompt="Say hello", actor=Actor("u"))
        d = self.cai.route(r)
        assert self.cai.escalate(d.model_id, d) not in (None, d.model_id)


class TestRiskClassification:
    def setup_method(self):
        self.cai = CostIntelligenceAI()

    def test_chitchat_is_class_a(self):
        assert self.cai.profile(Request(prompt="hi", actor=Actor("u"))).risk_class \
            is RiskClass.A

    def test_factual_is_class_b(self):
        p = self.cai.profile(Request(prompt="What is the balance on this account?",
                                     actor=Actor("u")))
        assert p.risk_class is RiskClass.B and p.is_factual

    def test_irreversible_action_is_class_c(self):
        p = self.cai.profile(Request(
            prompt="do it", actor=Actor("u"),
            proposed_action=ProposedAction("issue_refund", reversible=False,
                                           value_usd=5000)))
        assert p.risk_class is RiskClass.C
