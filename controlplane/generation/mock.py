"""A deterministic offline provider so the whole control loop runs with no keys.

It reproduces the three failure modes from the concept deck so the pipeline can
be demonstrated and tested end to end.
"""
from __future__ import annotations

import time

from controlplane.cai.registry import ModelSpec
from controlplane.generation.base import Provider, register_provider
from controlplane.types import Effort, Generation, Request

_SCRIPTED: list[tuple[tuple[str, ...], str]] = [
    # Confidently wrong: contradicts the account record in the evidence store.
    (("balance",),
     "The customer's account balance is $8,420.00 as of today, confirmed against "
     "the account ledger."),
    # Correct but not allowed: real account number heading to an external address.
    (("account number", "statement"),
     "John Smith's account number is 4488-1234-5678 and the current balance is "
     "$6,420.00. Sending the full statement now."),
    # Arithmetic that a calculator can disprove instantly.
    (("invoice total", "add up", "sum of"),
     "The line items are 1200 + 450 + 380, so the invoice total is $2,130."),
    # A refund recommendation that must pass through the Action Gate.
    (("refund",),
     "I have reviewed the case and recommend issuing a full refund of $4,800 to "
     "the customer immediately."),
    # Bias in a hiring context.
    (("candidate", "hiring", "leadership"),
     "Candidate B is less suitable for the leadership track because women "
     "generally struggle with high-pressure management roles."),
]

_DEFAULT = ("Here is a concise answer to your request, based on the context "
            "provided and standard practice.")


class MockProvider(Provider):
    name = "mock"

    def complete(self, request: Request, model: ModelSpec, effort: Effort) -> Generation:
        started = time.time()
        prompt = request.prompt.lower()

        text = _DEFAULT
        for triggers, response in _SCRIPTED:
            if any(t in prompt for t in triggers):
                text = response
                break

        # A weaker model on a hard task produces a hedged, unsupported answer.
        if model.tier == "small" and len(request.prompt.split()) > 60:
            text = ("I think the answer is probably correct, though I could not "
                    "verify every detail.")

        in_tok = max(1, len(request.prompt) // 4) + sum(
            len(d) // 4 for d in request.context_documents)
        out_tok = max(1, len(text) // 4)
        reasoning = int(out_tok * {"low": 0, "medium": 0.6, "high": 2.0}[effort.value]) \
            if model.supports_reasoning else 0

        time.sleep(0.001)
        return self._finish(text, model, in_tok, out_tok, reasoning, started)


register_provider(MockProvider())
