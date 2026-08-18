"""Anthropic provider.

TODO[FILL] -- this file is intentionally incomplete.
Fill `complete()` and the project runs against real Anthropic models with no other
change: add the model to config/models.yaml with `provider: anthropic`.

Reference implementation:

    from anthropic import Anthropic
    client = Anthropic(api_key=settings.anthropic_api_key)
    resp = client.chat.completions.create(
        model=model.id,
        messages=[{"role": "user", "content": request.prompt}],
        reasoning_effort=effort.value,          # omit for non-reasoning models
    )
    text = resp.choices[0].message.content
    in_tok = resp.usage.prompt_tokens
    out_tok = resp.usage.completion_tokens
    reasoning = getattr(resp.usage, "reasoning_tokens", 0) or 0
    return self._finish(text, model, in_tok, out_tok, reasoning, started)
"""
from __future__ import annotations

import time

from config.settings import settings
from controlplane.cai.registry import ModelSpec
from controlplane.generation.base import Provider, register_provider
from controlplane.types import Effort, Generation, Request


class AnthropicProvider(Provider):
    name = "anthropic"

    def complete(self, request: Request, model: ModelSpec, effort: Effort) -> Generation:
        started = time.time()
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Copy .env.example to .env and fill it, "
                "or run with CP_DEFAULT_PROVIDER=mock."
            )
        # TODO[FILL]: call the Anthropic API and return self._finish(...)
        raise NotImplementedError(
            "AnthropicProvider.complete() is a deliberate gap - see the docstring."
        )


register_provider(AnthropicProvider())
