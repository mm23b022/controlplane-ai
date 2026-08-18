"""CAI step 4 -> Route.

Selects the "Recommendable Model": the lowest-cost model that is *likely to
succeed*. This is explicitly NOT cheapest-first, because a failed cheap call
still burns tokens and then pays the expensive model anyway.
"""
from __future__ import annotations

from controlplane.cai.classifier import TaskClassifier
from controlplane.cai.estimator import (choose_effort, cost_per_success,
                                        estimate_cost, estimate_success)
from controlplane.cai.registry import ModelRegistry, registry as default_registry
from controlplane.types import Effort, Request, RoutingDecision, TaskProfile


class CostIntelligenceAI:
    """The CAI box in the architecture: understand -> know -> estimate -> route."""

    def __init__(self, registry: ModelRegistry | None = None,
                 classifier: TaskClassifier | None = None) -> None:
        self.registry = registry or default_registry
        self.classifier = classifier or TaskClassifier()

    def profile(self, request: Request) -> TaskProfile:
        return self.classifier.classify(request)

    def route(self, request: Request, profile: TaskProfile | None = None) -> RoutingDecision:
        profile = profile or self.profile(request)
        effort = choose_effort(profile)

        candidates = self.registry.eligible(
            modalities=profile.modalities,
            needs_reasoning=profile.needs_reasoning,
            min_context=profile.est_input_tokens + profile.est_output_tokens,
        )
        if not candidates:
            candidates = self.registry.all()

        scored = []
        for m in candidates:
            cost = estimate_cost(m, profile, effort)
            success = estimate_success(m, profile)
            scored.append({
                "model_id": m.id,
                "expected_cost_usd": round(cost, 6),
                "expected_success": success,
                "cost_per_success": round(cost_per_success(cost, success), 6),
                "tier": m.tier,
            })

        floor = self.registry.success_floor
        # High-consequence work raises the bar on reliability.
        if profile.risk_class.value == "C":
            floor = min(0.92, floor + 0.08)

        viable = [s for s in scored if s["expected_success"] >= floor]
        if viable:
            pick = min(viable, key=lambda s: s["expected_cost_usd"])
            rationale = (
                f"cheapest model clearing the {floor:.0%} success floor for a "
                f"{profile.task_type.value} task of complexity {profile.complexity}"
            )
        else:
            # Nothing clears the floor: fall back to best expected cost-per-success.
            pick = min(scored, key=lambda s: s["cost_per_success"])
            rationale = (
                f"no model cleared the {floor:.0%} floor; chose best expected "
                f"cost-per-successful-task"
            )

        best = max(scored, key=lambda s: s["expected_success"])
        cheaper_backup = sorted(scored, key=lambda s: s["expected_cost_usd"])
        fallback = next(
            (s["model_id"] for s in sorted(scored, key=lambda x: -x["expected_success"])
             if s["model_id"] != pick["model_id"]),
            None,
        )

        return RoutingDecision(
            model_id=pick["model_id"],
            effort=effort,
            expected_cost_usd=pick["expected_cost_usd"],
            expected_success=pick["expected_success"],
            rationale=rationale,
            best_model_id=best["model_id"],
            alternatives=sorted(scored, key=lambda s: s["cost_per_success"]),
            fallback_model_id=fallback,
        )

    def escalate(self, current_model_id: str, routing: RoutingDecision) -> str | None:
        """Failure-aware routing: escalate only when a check actually failed."""
        stronger = [a for a in routing.alternatives
                    if a["expected_success"] > routing.expected_success
                    and a["model_id"] != current_model_id]
        if not stronger:
            return None
        return min(stronger, key=lambda a: a["expected_cost_usd"])["model_id"]
