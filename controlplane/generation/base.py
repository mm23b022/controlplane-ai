"""Provider interface. ControlPlane is model-agnostic: anything implementing
this protocol can sit in the GENERATION box."""
from __future__ import annotations

import abc
import time

from controlplane.cai.registry import ModelSpec, registry
from controlplane.types import Effort, Generation, Request


class Provider(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def complete(self, request: Request, model: ModelSpec, effort: Effort) -> Generation:
        """Return a Generation. Implementations MUST set token counts so the
        cost checker can compare actual spend against the CAI estimate."""

    @staticmethod
    def _finish(text: str, model: ModelSpec, in_tok: int, out_tok: int,
                reasoning_tok: int, started: float) -> Generation:
        return Generation(
            text=text,
            model_id=model.id,
            input_tokens=in_tok,
            output_tokens=out_tok,
            reasoning_tokens=reasoning_tok,
            cost_usd=model.price(in_tok, out_tok, reasoning_tok),
            latency_ms=int((time.time() - started) * 1000),
            verified=False,   # OUTPUT = UNVERIFIED
        )


_PROVIDERS: dict[str, Provider] = {}


def register_provider(provider: Provider) -> None:
    _PROVIDERS[provider.name] = provider


def get_provider(name: str) -> Provider:
    if name not in _PROVIDERS:
        raise KeyError(
            f"Provider '{name}' is not registered. Implement it in "
            f"controlplane/generation/ and call register_provider()."
        )
    return _PROVIDERS[name]


def provider_for_model(model_id: str) -> Provider:
    return get_provider(registry.get(model_id).provider)
