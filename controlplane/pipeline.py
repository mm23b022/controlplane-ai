"""The ControlPlane loop.

    INPUT -> CAI -> GENERATION -> CHECKER -> DECISION -> ACTION GATE -> LEARNING

Everything else in this package is a component; this file is the control flow.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from config.settings import settings
from controlplane.action.gate import ActionGate
from controlplane.cai.registry import registry
from controlplane.cai.router import CostIntelligenceAI
from controlplane.checker.cost import CostChecker
from controlplane.checker.performance import PerformanceChecker
from controlplane.checker.responsibility import ResponsibilityChecker
from controlplane.checker.router import plan_for
from controlplane.decision.engine import DecisionEngine, apply_deterministic_edits
from controlplane.evidence.store import EvidenceStore, default_store
from controlplane.foundation.audit import audit_log
from controlplane.generation import provider_for_model
from controlplane.human.queue import review_queue
from controlplane.learning.feedback import learning_loop
from controlplane.types import (CheckResult, ControlEvent, ControlPlaneResponse,
                                Decision, Dimension, Generation, Request)


class ControlPlane:
    def __init__(self, evidence_store: EvidenceStore | None = None,
                 max_attempts: int | None = None) -> None:
        self.store = evidence_store or default_store
        self.cai = CostIntelligenceAI()
        self.performance = PerformanceChecker(store=self.store)
        self.cost = CostChecker()
        self.responsibility = ResponsibilityChecker()
        self.decisions = DecisionEngine()
        self.gate = ActionGate()
        self.max_attempts = max_attempts or settings.max_regeneration_attempts

    # ------------------------------------------------------------------
    def handle(self, request: Request) -> ControlPlaneResponse:
        t0 = time.time()

        # --- CAI: understand -> know -> estimate -> route -------------------
        profile = self.cai.profile(request)
        routing = self.cai.route(request, profile)
        model_id = routing.model_id

        attempts = 0
        generation: Generation | None = None
        results: list[CheckResult] = []
        control_decision = None
        total_generation_cost = 0.0

        while attempts < self.max_attempts + 1:
            attempts += 1

            # --- GENERATION: output is UNVERIFIED ---------------------------
            spec = registry.get(model_id)
            generation = provider_for_model(model_id).complete(
                request, spec, routing.effort)
            total_generation_cost += generation.cost_usd

            # --- CHECKER: adaptive depth, parallel, early exit --------------
            plan = plan_for(profile, generation.cost_usd)
            self.performance.verifier.available = (
                plan.allow_llm_verifier and self.performance.verifier.available)
            results = self._run_checks(request, generation, profile, routing, attempts)

            # --- DECISION ---------------------------------------------------
            control_decision = self.decisions.decide(request, profile, results, attempts)

            if control_decision.decision is not Decision.REGENERATE:
                break
            if attempts > self.max_attempts:
                break
            # Failure-aware routing: escalate only because a check failed.
            stronger = self.cai.escalate(model_id, routing)
            if stronger:
                model_id = stronger

        assert generation is not None and control_decision is not None

        # --- Deterministic EDIT (mask an ID); never patch bad reasoning -----
        answer = generation.text
        if control_decision.decision in (Decision.ALLOW, Decision.ANNOTATE):
            answer, edits = apply_deterministic_edits(answer, control_decision.findings)
            control_decision.edits_applied = edits

        # --- ACTION GATE ----------------------------------------------------
        gate_result = None
        if control_decision.decision in (Decision.ALLOW, Decision.ANNOTATE):
            gate_result = self.gate.evaluate(request, request.proposed_action)
            if not gate_result.allowed:
                control_decision.decision = gate_result.decision
                control_decision.reason = f"Action gate ({gate_result.stage}): {gate_result.reason}"
                control_decision.requires_human = gate_result.decision is Decision.HOLD
            elif request.proposed_action is not None:
                try:
                    gate_result.result = self.gate.execute(request.proposed_action)
                    gate_result.executed = True
                except KeyError as exc:
                    control_decision.decision = Decision.HOLD
                    control_decision.reason = str(exc)
                    control_decision.requires_human = True

        # --- HUMAN WHEN NEEDED ----------------------------------------------
        review_id = None
        if control_decision.decision is Decision.HOLD:
            item = review_queue.submit(
                request_id=request.request_id, prompt=request.prompt, answer=answer,
                reason=control_decision.reason,
                findings=[self._finding_dict(f) for f in control_decision.findings],
                proposed_action=(vars(request.proposed_action)
                                 if request.proposed_action else None))
            review_id = item.review_id

        # --- CONTROL EVENT: audit + learn -----------------------------------
        control_cost = sum(r.cost_usd for r in results)
        total_latency = int((time.time() - t0) * 1000)
        event = ControlEvent(
            request_id=request.request_id, prompt=request.prompt,
            actor_id=request.actor.user_id,
            routing={"model_id": model_id, "effort": routing.effort.value,
                     "expected_cost_usd": routing.expected_cost_usd,
                     "expected_success": routing.expected_success,
                     "rationale": routing.rationale},
            generation={"model_id": generation.model_id,
                        "input_tokens": generation.input_tokens,
                        "output_tokens": generation.output_tokens,
                        "cost_usd": generation.cost_usd},
            checks=[self._check_dict(r) for r in results],
            decision=control_decision.decision.value,
            reason=control_decision.reason,
            action_gate=({"stage": gate_result.stage, "allowed": gate_result.allowed,
                          "executed": gate_result.executed, "checks": gate_result.checks}
                         if gate_result else None),
            total_cost_usd=round(total_generation_cost + control_cost, 8),
            control_cost_usd=round(control_cost, 8),
            total_latency_ms=total_latency, attempts=attempts,
        )
        audit_log.write(event)
        learning_loop.record(event)

        return self._respond(request, control_decision, answer, results,
                             generation, model_id, event, review_id)

    # ------------------------------------------------------------------
    def _run_checks(self, request, generation, profile, routing, attempts
                    ) -> list[CheckResult]:
        """PARALLEL: independent checks run concurrently, not in sequence."""
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                Dimension.PERFORMANCE: pool.submit(
                    self.performance.check, request, generation, profile),
                Dimension.COST: pool.submit(
                    self.cost.check, request, generation, routing, attempts),
                Dimension.RESPONSIBILITY: pool.submit(
                    self.responsibility.check, request, generation),
            }
            return [f.result() for f in futures.values()]

    @staticmethod
    def _finding_dict(f) -> dict:
        return {"dimension": f.dimension.value, "category": f.category,
                "severity": f.severity.value, "confidence": f.confidence,
                "message": f.message, "deterministic": f.deterministic}

    def _check_dict(self, r: CheckResult) -> dict:
        return {"dimension": r.dimension.value, "checks_run": r.checks_run,
                "early_exit": r.early_exit, "cost_usd": r.cost_usd,
                "latency_ms": r.latency_ms,
                "findings": [self._finding_dict(f) for f in r.findings]}

    def _respond(self, request, decision, answer, results, generation,
                 model_id, event, review_id) -> ControlPlaneResponse:
        perf = next(r for r in results if r.dimension is Dimension.PERFORMANCE)
        resp_check = next(r for r in results if r.dimension is Dimension.RESPONSIBILITY)
        cost_check = next(r for r in results if r.dimension is Dimension.COST)

        status = "VERIFIED"
        if any(f.category in ("contradicted_by_source", "arithmetic_error")
               for f in perf.findings):
            status = "CONTRADICTED"
        elif any(f.category == "unsupported_claim" for f in perf.findings):
            status = "UNCERTAIN"

        citations = []
        if decision.decision in (Decision.ALLOW, Decision.ANNOTATE):
            citations = [p.doc_id for p in self.store.retrieve(request.prompt, k=3)]

        blocked = decision.decision in (Decision.BLOCK, Decision.HOLD)
        warning = None
        if decision.decision is Decision.BLOCK:
            warning = "Response blocked by ControlPlane: " + decision.reason
        elif decision.decision is Decision.HOLD:
            warning = "Held for human review: " + decision.reason
        elif decision.annotations:
            warning = decision.annotations[0]

        return ControlPlaneResponse(
            request_id=request.request_id,
            decision=decision.decision,
            answer=None if blocked else answer,
            annotations=decision.annotations,
            citations=citations,
            verification_status=status,
            warning=warning,
            details={
                "model_id": model_id,
                "verification_status_responsibility":
                    ResponsibilityChecker.status(resp_check),
                "cost_status": CostChecker.status(cost_check),
                "total_cost_usd": event.total_cost_usd,
                "control_cost_usd": event.control_cost_usd,
                "control_overhead_pct": (
                    round(100 * event.control_cost_usd /
                          max(event.total_cost_usd, 1e-9), 2)),
                "latency_ms": event.total_latency_ms,
                "attempts": event.attempts,
                "checks_run": {r.dimension.value: r.checks_run for r in results},
                "early_exit": any(r.early_exit for r in results),
                "edits_applied": decision.edits_applied,
                "review_id": review_id,
                "reason": decision.reason,
            },
        )
