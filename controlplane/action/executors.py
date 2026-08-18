"""Real side-effecting executors.

TODO[FILL] -- deliberately empty. These are the functions that actually move
money, send mail and mutate records. They run ONLY after ActionGate.evaluate()
returns allowed=True.

Register one per action name in config/policies.yaml -> actions:

    def issue_refund(order_id: str, amount_usd: float) -> dict:
        resp = payments_client.refund(order_id=order_id, amount=amount_usd)
        return {"refund_id": resp.id, "status": resp.status}

    EXECUTORS = {"issue_refund": issue_refund, ...}

Two rules:
  1. Never call these directly. Always go through ActionGate.
  2. Every executor must be idempotent on `request_id` so a retry after a HOLD
     cannot double-charge.
"""
from __future__ import annotations

from typing import Any, Callable


def _demo_read_account(account_id: str = "") -> dict[str, Any]:
    """A safe, read-only example so the gate can be demonstrated end to end."""
    return {"account_id": account_id, "status": "ok", "note": "demo executor"}


EXECUTORS: dict[str, Callable[..., Any]] = {
    "read_account": _demo_read_account,
    # TODO[FILL]: "issue_refund": issue_refund,
    # TODO[FILL]: "send_email": send_email,
}
