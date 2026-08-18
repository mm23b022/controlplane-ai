"""CAI step 3 -> Estimate cost and probability of success before running."""
from __future__ import annotations

from controlplane.cai.registry import ModelSpec
from controlplane.types import Effort, TaskProfile

_EFFORT_MULTIPLIER = {Effort.LOW: 0.0, Effort.MEDIUM: 0.6, Effort.HIGH: 2.0}


def choose_effort(profile: TaskProfile) -> Effort:
    """Don't pay for reasoning tokens on simple tasks."""
    if profile.complexity < 0.3 and not profile.needs_reasoning:
        return Effort.LOW
    if profile.complexity > 0.7 or profile.risk_class.value == "C":
        return Effort.HIGH
    return Effort.MEDIUM


def estimate_cost(model: ModelSpec, profile: TaskProfile, effort: Effort) -> float:
    reasoning = 0
    if model.supports_reasoning:
        reasoning = int(profile.est_output_tokens * _EFFORT_MULTIPLIER[effort])
    return model.price(profile.est_input_tokens, profile.est_output_tokens, reasoning)


def estimate_success(model: ModelSpec, profile: TaskProfile) -> float:
    """P(model completes THIS task), not 'how smart is this model'.

    Skill is discounted by task complexity: a weak model degrades sharply as the
    task gets harder, a strong model barely moves.
    """
    skill = model.skill_for(profile.task_type.value)
    penalty = profile.complexity * (1.0 - skill) * 1.15
    p = skill - penalty
    if profile.needs_reasoning and not model.supports_reasoning:
        p -= 0.25
    return round(max(0.01, min(0.99, p)), 4)


def cost_per_success(cost: float, success: float) -> float:
    """The metric that matters: expected spend per *successfully completed* task."""
    return cost / max(success, 0.01)
