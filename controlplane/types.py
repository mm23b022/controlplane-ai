"""Core domain types shared by every layer of ControlPlane.

These mirror the architecture diagram 1:1:
    INPUT -> CAI -> GENERATION -> CHECKER -> DECISION -> ACTION GATE -> LEARNING
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------
class Decision(str, Enum):
    """The five outcomes of the Decision Engine."""
    ALLOW = "ALLOW"
    ANNOTATE = "ANNOTATE"
    REGENERATE = "REGENERATE"
    HOLD = "HOLD"
    BLOCK = "BLOCK"


class Dimension(str, Enum):
    PERFORMANCE = "PERFORMANCE"
    COST = "COST"
    RESPONSIBILITY = "RESPONSIBILITY"


class Severity(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        return {"NONE": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}[self.value]


class RiskClass(str, Enum):
    """Verification depth. Class A is the fast path, Class C is high consequence."""
    A = "A"  # simple / low risk      -> deterministic checks only
    B = "B"  # factual                -> + evidence grounding
    C = "C"  # high risk / actionable -> + verifier, possibly human


class TaskType(str, Enum):
    CONVERSATION = "conversation"
    SUMMARIZATION = "summarization"
    EXTRACTION = "extraction"
    CLASSIFICATION = "classification"
    WRITING = "writing"
    CODING = "coding"
    REASONING = "reasoning"
    COMPLEX_REASONING = "complex_reasoning"
    DATA_ANALYSIS = "data_analysis"
    TOOL_EXECUTION = "tool_execution"


class Effort(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# --------------------------------------------------------------------------
# Request / context
# --------------------------------------------------------------------------
@dataclass
class Actor:
    """Who is asking. Responsibility decisions depend on this, not just on text."""
    user_id: str
    role: str = "user"                    # user | agent | support_agent | admin
    permissions: list[str] = field(default_factory=list)

    def has(self, permission: str) -> bool:
        return permission in self.permissions or "*" in self.permissions


@dataclass
class Destination:
    """Where the output is going. `external=True` flips many privacy verdicts."""
    channel: str = "chat"                 # chat | email | webhook | api | file
    external: bool = False
    address: str | None = None


@dataclass
class ProposedAction:
    """A side-effecting action the model wants to take (checked by the Action Gate)."""
    name: str                             # e.g. "issue_refund"
    parameters: dict[str, Any] = field(default_factory=dict)
    reversible: bool = True
    value_usd: float = 0.0


@dataclass
class Request:
    prompt: str
    actor: Actor
    destination: Destination = field(default_factory=Destination)
    context_documents: list[str] = field(default_factory=list)
    proposed_action: ProposedAction | None = None
    max_cost_usd: float | None = None     # per-request verification budget
    max_latency_ms: int | None = None
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    metadata: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
# CAI output
# --------------------------------------------------------------------------
@dataclass
class TaskProfile:
    task_type: TaskType
    complexity: float                     # 0..1
    needs_reasoning: bool
    modalities: list[str] = field(default_factory=lambda: ["text"])
    est_input_tokens: int = 0
    est_output_tokens: int = 0
    risk_class: RiskClass = RiskClass.A
    is_factual: bool = False


@dataclass
class RoutingDecision:
    """The 'Recommendable Model' — cheapest model *likely to succeed*."""
    model_id: str
    effort: Effort
    expected_cost_usd: float
    expected_success: float
    rationale: str
    best_model_id: str | None = None      # highest-capability suitable option
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    fallback_model_id: str | None = None


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------
@dataclass
class Generation:
    text: str
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    verified: bool = False                # OUTPUT = UNVERIFIED until the checker clears it


# --------------------------------------------------------------------------
# Checker output
# --------------------------------------------------------------------------
@dataclass
class Finding:
    """A detector emits findings. It never decides — the Decision Engine does."""
    dimension: Dimension
    category: str                         # "hallucination", "pii", "over_budget", ...
    severity: Severity
    confidence: float                     # 0..1, how sure the detector is
    message: str
    evidence: str | None = None
    deterministic: bool = False           # proved by a tool, not inferred by a model
    recommended: Decision | None = None
    fixable: bool = False                 # can a regeneration plausibly fix this?
    deterministic_fix: str | None = None  # set only when an EDIT is safe

    @property
    def decisive(self) -> bool:
        """A deterministic CRITICAL finding permits early exit — no verifier needed."""
        return self.deterministic and self.severity is Severity.CRITICAL


@dataclass
class CheckResult:
    dimension: Dimension
    findings: list[Finding] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    latency_ms: int = 0
    early_exit: bool = False

    @property
    def worst(self) -> Severity:
        return max((f.severity for f in self.findings), default=Severity.NONE, key=lambda s: s.rank)


# --------------------------------------------------------------------------
# Decision + final result
# --------------------------------------------------------------------------
@dataclass
class ControlDecision:
    decision: Decision
    reason: str
    findings: list[Finding] = field(default_factory=list)
    annotations: list[str] = field(default_factory=list)
    edits_applied: list[str] = field(default_factory=list)
    requires_human: bool = False


@dataclass
class ControlEvent:
    """The audit + learning record. Written for every request, always."""
    request_id: str
    prompt: str
    actor_id: str
    routing: dict[str, Any]
    generation: dict[str, Any]
    checks: list[dict[str, Any]]
    decision: str
    reason: str
    action_gate: dict[str, Any] | None
    total_cost_usd: float
    control_cost_usd: float
    total_latency_ms: int
    attempts: int
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ControlPlaneResponse:
    """What the caller finally receives (the FINAL OUTPUT box)."""
    request_id: str
    decision: Decision
    answer: str | None
    annotations: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    verification_status: str = "UNVERIFIED"
    warning: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
