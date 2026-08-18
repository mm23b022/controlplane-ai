"""CAI step 1 -> Understand the task.

A deliberately cheap heuristic classifier. It never calls an LLM, because the
whole point of CAI is to decide routing *before* spending generation tokens.
"""
from __future__ import annotations

import re

from controlplane.types import Request, RiskClass, TaskProfile, TaskType

_KEYWORDS: list[tuple[TaskType, tuple[str, ...]]] = [
    (TaskType.CODING, ("code", "function", "bug", "refactor", "python", "sql", "compile")),
    (TaskType.SUMMARIZATION, ("summarise", "summarize", "summary", "tl;dr", "condense")),
    (TaskType.EXTRACTION, ("extract", "pull out", "list the", "parse", "field")),
    (TaskType.CLASSIFICATION, ("classify", "categorise", "categorize", "label", "sentiment")),
    (TaskType.DATA_ANALYSIS, ("analyse", "analyze", "trend", "chart", "metric", "revenue")),
    (TaskType.COMPLEX_REASONING, ("prove", "derive", "optimise", "strategy", "trade-off", "why does")),
    (TaskType.REASONING, ("explain", "compare", "evaluate", "reason", "decide")),
    (TaskType.WRITING, ("write", "draft", "email", "blog", "post", "letter")),
]

# Signals that the answer will contain checkable facts (-> evidence grounding).
_FACTUAL = ("balance", "revenue", "how many", "what is the", "when did", "who is",
            "price", "total", "amount", "figure", "statistic", "according to")

# Signals of consequence (-> deeper verification, Class C).
_HIGH_RISK = ("refund", "payment", "transfer", "approve", "delete", "terminate",
              "medical", "diagnosis", "legal", "hire", "fire", "loan", "credit")


def _estimate_tokens(text: str) -> int:
    """~4 characters per token is close enough for routing decisions."""
    return max(1, len(text) // 4)


class TaskClassifier:
    def classify(self, request: Request) -> TaskProfile:
        text = request.prompt.lower()

        task_type = TaskType.CONVERSATION
        for candidate, words in _KEYWORDS:
            if any(w in text for w in words):
                task_type = candidate
                break

        words = len(request.prompt.split())
        complexity = min(1.0, words / 220)
        if task_type in (TaskType.COMPLEX_REASONING, TaskType.CODING):
            complexity = min(1.0, complexity + 0.45)
        elif task_type in (TaskType.REASONING, TaskType.DATA_ANALYSIS):
            complexity = min(1.0, complexity + 0.25)
        if re.search(r"\d+\s*[\+\-\*/%]\s*\d+", request.prompt):
            complexity = min(1.0, complexity + 0.1)

        is_factual = any(k in text for k in _FACTUAL) or bool(request.context_documents)
        high_risk = any(k in text for k in _HIGH_RISK)

        if request.proposed_action is not None or high_risk:
            risk = RiskClass.C
        elif is_factual:
            risk = RiskClass.B
        else:
            risk = RiskClass.A

        # An irreversible or high-value action always forces the deepest path.
        if request.proposed_action and (
            not request.proposed_action.reversible or request.proposed_action.value_usd > 1000
        ):
            risk = RiskClass.C

        ctx_tokens = sum(_estimate_tokens(d) for d in request.context_documents)
        est_in = _estimate_tokens(request.prompt) + ctx_tokens
        est_out = int(120 + complexity * 900)

        return TaskProfile(
            task_type=task_type,
            complexity=round(complexity, 3),
            needs_reasoning=complexity > 0.6 or task_type is TaskType.COMPLEX_REASONING,
            modalities=["text"],
            est_input_tokens=est_in,
            est_output_tokens=est_out,
            risk_class=risk,
            is_factual=is_factual,
        )
