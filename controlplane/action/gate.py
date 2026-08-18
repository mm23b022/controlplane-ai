"""ACTION GATE -- nothing consequential executes without a final control check.

This is the layer that governs the ACTION, not the sentence. Even a response the
checker cleared must pass intent -> permission -> risk -> policy before execute.
An action absent from config/policies.yaml is DENIED (fail closed).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from config.settings import policies
from controlplane.types import Decision, ProposedAction, Request


@dataclass
class GateResult:
    allowed: bool
    decision: Decision
    stage: str                       # which stage settled it
    reason: str
    checks: list[dict] = field(default_factory=list)
    executed: bool = False
    result: object | None = None


class ActionGate:
    STAGES = ("intent", "permission", "risk", "policy", "execute")

    def __init__(self, executors: dict | None = None) -> None:
        from controlplane.action.executors import EXECUTORS
        self.executors = executors if executors is not None else EXECUTORS

    def evaluate(self, request: Request, action: ProposedAction | None) -> GateResult:
        checks: list[dict] = []
        if action is None:
            return GateResult(True, Decision.ALLOW, "intent",
                              "No side-effecting action proposed.", checks)

        rules = policies().get("actions", {})

        # --- 1. INTENT: is this action even registered? --------------------
        spec = rules.get(action.name)
        checks.append({"stage": "intent", "action": action.name,
                       "registered": spec is not None})
        if spec is None:
            return GateResult(False, Decision.BLOCK, "intent",
                              f"Action '{action.name}' is not registered in policy. "
                              f"Denied by default.", checks)

        # --- 2. PERMISSION -------------------------------------------------
        needed = spec.get("required_permission")
        has = request.actor.has(needed) if needed else True
        checks.append({"stage": "permission", "required": needed, "granted": has})
        if not has:
            return GateResult(False, Decision.BLOCK, "permission",
                              f"Actor '{request.actor.user_id}' lacks "
                              f"'{needed}'.", checks)

        # --- 3. RISK -------------------------------------------------------
        hard_limit = float(spec.get("hard_limit_usd", 0) or 0)
        value = float(action.value_usd or 0)
        checks.append({"stage": "risk", "value_usd": value,
                       "hard_limit_usd": hard_limit,
                       "reversible": action.reversible})
        if hard_limit and value > hard_limit:
            return GateResult(False, Decision.BLOCK, "risk",
                              f"${value:,.2f} exceeds the hard limit of "
                              f"${hard_limit:,.2f}.", checks)

        # --- 4. POLICY: approval thresholds --------------------------------
        auto = float(spec.get("auto_approve_below_usd", 0) or 0)
        needs_approval = value >= auto
        checks.append({"stage": "policy", "auto_approve_below_usd": auto,
                       "needs_human_approval": needs_approval})
        if needs_approval:
            return GateResult(False, Decision.HOLD, "policy",
                              f"${value:,.2f} is at or above the auto-approval "
                              f"threshold of ${auto:,.2f}; human approval required.",
                              checks)

        # --- 5. EXECUTE ----------------------------------------------------
        checks.append({"stage": "execute", "reached": True})
        return GateResult(True, Decision.ALLOW, "execute",
                          "All gate stages passed.", checks)

    def execute(self, action: ProposedAction) -> object:
        executor = self.executors.get(action.name)
        if executor is None:
            raise KeyError(
                f"No executor registered for '{action.name}'. "
                f"Add one in controlplane/action/executors.py."
            )
        return executor(**action.parameters)
