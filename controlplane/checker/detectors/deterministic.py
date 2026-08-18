"""Deterministic detectors: a calculator and a schema validator.

DETERMINISTIC-FIRST is the core latency strategy. If a calculator can prove the
maths is wrong, no verifier LLM is ever called -- the check exits early.
"""
from __future__ import annotations

import ast
import operator
import re

from controlplane.types import Decision, Dimension, Finding, Severity

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.USub: operator.neg}

# "1200 + 450 + 380, so the invoice total is $2,130"
_ARITHMETIC = re.compile(
    r"(?P<expr>\d[\d\s,]*(?:[\+\-\*/]\s*[\d,\.]+\s*)+)"
    r"[^\d]{0,60}?"
    r"(?:is|=|equals|total(?:s| is)?)\s*\$?\s*(?P<claim>[\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("unsupported expression")


def _looks_like_identifier(expr: str) -> bool:
    """'4488-1234-5678' is an account number, not a subtraction.

    Real arithmetic in model output is written with spaces around operators;
    identifiers are hyphen-joined with none. Without this guard the calculator
    reports false positives on account numbers, dates and phone numbers.
    """
    compact = expr.replace(" ", "")
    if "-" in compact and " " not in expr.strip():
        return True
    # Three or more hyphen-joined groups of 2+ digits is an ID pattern.
    return bool(re.fullmatch(r"\d{2,}(?:\s*-\s*\d{2,}){2,}", expr.strip()))


def check_arithmetic(text: str) -> list[Finding]:
    """Re-run any arithmetic the model asserted. Never trust it, compute it."""
    findings: list[Finding] = []
    for m in _ARITHMETIC.finditer(text):
        raw_expr = m.group("expr")
        if _looks_like_identifier(raw_expr):
            continue
        expr = raw_expr.replace(",", "").strip().rstrip("+-*/ ")
        claimed_raw = m.group("claim").replace(",", "")
        try:
            actual = _safe_eval(ast.parse(expr, mode="eval"))
            claimed = float(claimed_raw)
        except Exception:
            continue
        if abs(actual - claimed) > max(0.01, abs(actual) * 1e-6):
            findings.append(Finding(
                dimension=Dimension.PERFORMANCE,
                category="arithmetic_error",
                severity=Severity.CRITICAL,
                confidence=1.0,
                message=f"Model asserted {expr} = {claimed:g}, calculator returns {actual:g}.",
                evidence=m.group(0)[:160],
                deterministic=True,
                recommended=Decision.REGENERATE,
                fixable=True,
            ))
    return findings


def check_schema(text: str, required_fields: list[str]) -> list[Finding]:
    """Cheap structural validation for extraction-style tasks."""
    missing = [f for f in required_fields if f.lower() not in text.lower()]
    if not missing:
        return []
    return [Finding(
        dimension=Dimension.PERFORMANCE,
        category="schema_violation",
        severity=Severity.MEDIUM,
        confidence=1.0,
        message=f"Required field(s) missing from output: {', '.join(missing)}.",
        deterministic=True,
        recommended=Decision.REGENERATE,
        fixable=True,
    )]
