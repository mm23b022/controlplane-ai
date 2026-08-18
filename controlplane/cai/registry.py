"""Model & pricing registry, loaded from config/models.yaml."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config.settings import models_config


@dataclass
class ModelSpec:
    id: str
    provider: str
    tier: str
    input_price: float          # USD per 1M input tokens
    output_price: float         # USD per 1M output tokens
    context_window: int
    avg_latency_ms: int
    supports_reasoning: bool
    modalities: list[str]
    skills: dict[str, float] = field(default_factory=dict)

    def skill_for(self, task_type: str) -> float:
        return self.skills.get(task_type, 0.5)

    def price(self, in_tokens: int, out_tokens: int, reasoning_tokens: int = 0) -> float:
        return (
            in_tokens * self.input_price / 1_000_000
            + (out_tokens + reasoning_tokens) * self.output_price / 1_000_000
        )


class ModelRegistry:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or models_config()
        self._models = {m["id"]: ModelSpec(**m) for m in cfg.get("models", [])}
        self.success_floor: float = cfg.get("success_floor", 0.8)
        self.verification_budget: dict[str, float] = cfg.get("verification_budget", {})

    def get(self, model_id: str) -> ModelSpec:
        if model_id not in self._models:
            raise KeyError(f"Unknown model '{model_id}'. Add it to config/models.yaml.")
        return self._models[model_id]

    def all(self) -> list[ModelSpec]:
        return list(self._models.values())

    def eligible(self, modalities: list[str], needs_reasoning: bool,
                 min_context: int = 0) -> list[ModelSpec]:
        out = []
        for m in self._models.values():
            if not set(modalities).issubset(set(m.modalities)):
                continue
            if needs_reasoning and not m.supports_reasoning:
                continue
            if m.context_window < min_context:
                continue
            out.append(m)
        return out


registry = ModelRegistry()
