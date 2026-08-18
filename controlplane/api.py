"""HTTP surface. `uvicorn controlplane.api:app --reload`"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from controlplane.evidence.store import default_store
from controlplane.foundation.audit import audit_log
from controlplane.human.queue import review_queue
from controlplane.learning.feedback import learning_loop
from controlplane.pipeline import ControlPlane
from controlplane.types import Actor, Destination, ProposedAction, Request

app = FastAPI(title="ControlPlane", version="0.1.0",
              description="The control layer between AI output and consequence.")
plane = ControlPlane()


class ActorIn(BaseModel):
    user_id: str
    role: str = "user"
    permissions: list[str] = Field(default_factory=list)


class DestinationIn(BaseModel):
    channel: str = "chat"
    external: bool = False
    address: str | None = None


class ActionIn(BaseModel):
    name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    reversible: bool = True
    value_usd: float = 0.0


class RequestIn(BaseModel):
    prompt: str
    actor: ActorIn
    destination: DestinationIn = Field(default_factory=DestinationIn)
    context_documents: list[str] = Field(default_factory=list)
    proposed_action: ActionIn | None = None
    max_cost_usd: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewIn(BaseModel):
    status: str
    reviewer: str
    note: str = ""
    edited_answer: str | None = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/v1/complete")
def complete(body: RequestIn) -> dict:
    req = Request(
        prompt=body.prompt,
        actor=Actor(**body.actor.model_dump()),
        destination=Destination(**body.destination.model_dump()),
        context_documents=body.context_documents,
        proposed_action=(ProposedAction(**body.proposed_action.model_dump())
                         if body.proposed_action else None),
        max_cost_usd=body.max_cost_usd,
        metadata=body.metadata,
    )
    resp = plane.handle(req)
    return {
        "request_id": resp.request_id,
        "decision": resp.decision.value,
        "answer": resp.answer,
        "annotations": resp.annotations,
        "citations": resp.citations,
        "verification_status": resp.verification_status,
        "warning": resp.warning,
        "details": resp.details,
    }


@app.get("/v1/events/{request_id}")
def get_event(request_id: str) -> dict:
    event = audit_log.get(request_id)
    if not event:
        raise HTTPException(404, "No control event with that request_id")
    return event


@app.get("/v1/events")
def recent_events(limit: int = 25) -> list[dict]:
    return audit_log.recent(limit)


@app.get("/v1/stats")
def stats() -> dict:
    return {"audit": audit_log.stats(), "reviews": review_queue.stats(),
            "learning": learning_loop.snapshot()}


@app.get("/v1/reviews")
def pending_reviews() -> list[dict]:
    return [vars(i) for i in review_queue.pending()]


@app.post("/v1/reviews/{review_id}")
def resolve_review(review_id: str, body: ReviewIn) -> dict:
    if not review_queue.get(review_id):
        raise HTTPException(404, "No such review")
    item = review_queue.resolve(review_id, body.status, body.reviewer,
                                body.note, body.edited_answer)
    for f in item.findings:
        learning_loop.record_review(f.get("category", "unknown"),
                                    upheld=body.status != "APPROVED")
    return vars(item)


class DocIn(BaseModel):
    doc_id: str
    text: str
    source: str = "corpus"
    authoritative: bool = False


@app.post("/v1/evidence")
def add_evidence(body: DocIn) -> dict:
    default_store.add(body.doc_id, body.text, body.source, body.authoritative)
    return {"status": "added", "doc_id": body.doc_id}
