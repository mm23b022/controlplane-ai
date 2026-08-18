"""Verification router: decides HOW DEEP to check, before checking.

This is the answer to "how do you avoid slowing the AI down":
risk sets verification depth, and low-risk traffic never pays for a verifier.
"""
from __future__ import annotations

from dataclasses import dataclass

from controlplane.cai.registry import registry
from controlplane.types import RiskClass, TaskProfile


@dataclass
class VerificationPlan:
    risk_class: RiskClass
    run_performance: bool
    run_cost: bool
    run_responsibility: bool
    allow_llm_verifier: bool
    allow_human: bool
    max_verification_cost_usd: float
    parallel: bool = True

    @property
    def label(self) -> str:
        return {RiskClass.A: "FAST PATH", RiskClass.B: "STANDARD PATH",
                RiskClass.C: "HIGH-RISK PATH"}[self.risk_class]


def plan_for(profile: TaskProfile, generation_cost: float) -> VerificationPlan:
    budgets = registry.verification_budget
    ratio = budgets.get(profile.risk_class.value, 0.5)
    budget = max(generation_cost * ratio, 1e-6)

    if profile.risk_class is RiskClass.A:
        return VerificationPlan(profile.risk_class, True, True, True,
                                allow_llm_verifier=False, allow_human=False,
                                max_verification_cost_usd=budget)
    if profile.risk_class is RiskClass.B:
        return VerificationPlan(profile.risk_class, True, True, True,
                                allow_llm_verifier=True, allow_human=False,
                                max_verification_cost_usd=budget)
    return VerificationPlan(profile.risk_class, True, True, True,
                            allow_llm_verifier=True, allow_human=True,
                            max_verification_cost_usd=budget)
