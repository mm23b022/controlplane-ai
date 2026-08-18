"""COST -- "Did we spend more than necessary?"

Note this is an *observer*, not a gate: it compares actual usage against the CAI
estimate and reports inefficiency. It never blocks an answer for being pricey.
"""
from __future__ import annotations

import time

from controlplane.types import (CheckResult, Decision, Dimension, Finding, Generation,
                                Request, RoutingDecision, Severity)


class CostChecker:
    def __init__(self, above_target: float = 1.5, over_budget: float = 3.0) -> None:
        self.above_target = above_target      # x estimate -> ABOVE TARGET
        self.over_budget = over_budget        # x estimate -> OVER BUDGET

    def check(self, request: Request, generation: Generation,
              routing: RoutingDecision, attempts: int = 1) -> CheckResult:
        started = time.time()
        result = CheckResult(dimension=Dimension.COST)
        result.checks_run.append("count_usage")

        estimate = max(routing.expected_cost_usd, 1e-9)
        ratio = generation.cost_usd / estimate
        result.checks_run.append("compare_to_estimate")

        if ratio >= self.over_budget:
            result.findings.append(Finding(
                dimension=Dimension.COST, category="over_budget",
                severity=Severity.MEDIUM, confidence=1.0,
                message=(f"Spend ${generation.cost_usd:.6f} is {ratio:.1f}x the CAI "
                         f"estimate of ${estimate:.6f}."),
                deterministic=True, recommended=Decision.ALLOW))
        elif ratio >= self.above_target:
            result.findings.append(Finding(
                dimension=Dimension.COST, category="above_target",
                severity=Severity.LOW, confidence=1.0,
                message=f"Spend is {ratio:.1f}x the CAI estimate.",
                deterministic=True, recommended=Decision.ALLOW))

        # Rework is the expensive failure mode: retries mean CAI mis-routed.
        result.checks_run.append("spot_rework")
        if attempts > 1:
            result.findings.append(Finding(
                dimension=Dimension.COST, category="rework",
                severity=Severity.MEDIUM, confidence=1.0,
                message=(f"{attempts} generation attempts were needed; routing "
                         f"should learn from this."),
                deterministic=True, recommended=Decision.ALLOW))

        # Over-thinking: paying for reasoning tokens far beyond the answer.
        if generation.reasoning_tokens > max(50, generation.output_tokens * 3):
            result.findings.append(Finding(
                dimension=Dimension.COST, category="over_thinking",
                severity=Severity.LOW, confidence=0.9,
                message=(f"{generation.reasoning_tokens} reasoning tokens for "
                         f"{generation.output_tokens} output tokens."),
                deterministic=True, recommended=Decision.ALLOW))

        result.checks_run.append("enforce_budget")
        if request.max_cost_usd is not None and generation.cost_usd > request.max_cost_usd:
            result.findings.append(Finding(
                dimension=Dimension.COST, category="budget_exceeded",
                severity=Severity.HIGH, confidence=1.0,
                message=(f"Request budget ${request.max_cost_usd:.6f} exceeded "
                         f"(spent ${generation.cost_usd:.6f})."),
                deterministic=True, recommended=Decision.HOLD))

        result.latency_ms = int((time.time() - started) * 1000)
        return result

    @staticmethod
    def status(result: CheckResult) -> str:
        cats = {f.category for f in result.findings}
        if "budget_exceeded" in cats or "over_budget" in cats:
            return "OVER BUDGET"
        if cats:
            return "ABOVE TARGET"
        return "WITHIN TARGET"
