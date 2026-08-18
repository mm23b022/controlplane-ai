"""RESPONSIBILITY -- "Is it safe, fair and allowed?"

Independent of PERFORMANCE. A response can be entirely correct and still be
prohibited. The verdict depends on:
    DATA + USER + ROLE + RECIPIENT + PURPOSE + POLICY
"""
from __future__ import annotations

import time

from config.settings import policies
from controlplane.checker.detectors import fairness, injection, pii
from controlplane.types import (CheckResult, Decision, Dimension, Finding, Generation,
                                Request, Severity)

_SEV = {"LOW": Severity.LOW, "MEDIUM": Severity.MEDIUM,
        "HIGH": Severity.HIGH, "CRITICAL": Severity.CRITICAL}


class ResponsibilityChecker:
    def check(self, request: Request, generation: Generation) -> CheckResult:
        started = time.time()
        result = CheckResult(dimension=Dimension.RESPONSIBILITY)
        cfg = policies()

        # --- Privacy & data (deterministic scanner + contextual policy) -------
        result.checks_run.append("privacy")
        result.findings += self._privacy(request, generation.text, cfg)

        # --- Safety (deterministic hard rules) -------------------------------
        result.checks_run.append("safety")
        result.findings += self._safety(generation.text, cfg)

        # --- Security / prompt injection -------------------------------------
        result.checks_run.append("security")
        result.findings += injection.scan(generation.text, source="model output")
        for doc in request.context_documents:
            result.findings += injection.scan(doc, source="retrieved context")

        # --- Fairness ---------------------------------------------------------
        result.checks_run.append("fairness")
        context = request.metadata.get("decision_context", "") or request.prompt
        result.findings += fairness.scan(generation.text, context)

        # EARLY EXIT: a deterministic critical breach is already proven.
        if any(f.decisive for f in result.findings):
            result.early_exit = True

        result.latency_ms = int((time.time() - started) * 1000)
        return result

    # ------------------------------------------------------------------
    def _privacy(self, request: Request, text: str, cfg: dict) -> list[Finding]:
        privacy_cfg = cfg.get("privacy", {})
        classes = privacy_cfg.get("classes", {})
        internal_roles = privacy_cfg.get("internal_roles", [])

        external = request.destination.external
        role_is_internal = request.actor.role in internal_roles

        findings: list[Finding] = []
        for hit in pii.scan(text):
            rule = classes.get(hit["class"])
            if rule is None:
                # Unknown identifier class: fail safe, flag for review.
                findings.append(Finding(
                    dimension=Dimension.RESPONSIBILITY, category="unclassified_pii",
                    severity=Severity.MEDIUM, confidence=0.6,
                    message=f"Unclassified identifier '{hit['class']}' in output.",
                    recommended=Decision.HOLD))
                continue

            allowed = rule.get("allow_external") if external else (
                rule.get("allow_internal") and role_is_internal)

            if allowed:
                continue

            where = "an external recipient" if external else \
                    f"a '{request.actor.role}' who is not an authorised internal role"
            severity = _SEV.get(str(rule.get("severity", "HIGH")).upper(), Severity.HIGH)
            findings.append(Finding(
                dimension=Dimension.RESPONSIBILITY,
                category="data_leakage",
                severity=severity,
                confidence=0.98,
                message=(f"{hit['class'].replace('_', ' ').title()} would be disclosed "
                         f"to {where}."),
                evidence=hit["value"][:40],
                deterministic=True,
                recommended=Decision.BLOCK if severity is Severity.CRITICAL
                            else Decision.REGENERATE,
                fixable=True,
                # Masking is a safe, deterministic EDIT.
                deterministic_fix=f"redact:{hit['class']}",
            ))
        return findings

    @staticmethod
    def _safety(text: str, cfg: dict) -> list[Finding]:
        low = text.lower()
        out = []
        for pattern in cfg.get("safety", {}).get("hard_block_patterns", []):
            if pattern.lower() in low:
                out.append(Finding(
                    dimension=Dimension.RESPONSIBILITY, category="unsafe_content",
                    severity=Severity.CRITICAL, confidence=1.0,
                    message=f"Output matches a prohibited-content rule ('{pattern}').",
                    deterministic=True, recommended=Decision.BLOCK))
        return out

    @staticmethod
    def status(result: CheckResult) -> str:
        worst = result.worst
        if worst.rank >= Severity.CRITICAL.rank:
            return "PROHIBITED"
        if worst.rank >= Severity.MEDIUM.rank:
            return "RESTRICTED"
        return "PERMITTED"
