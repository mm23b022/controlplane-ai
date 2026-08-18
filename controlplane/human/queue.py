"""HUMAN WHEN NEEDED -- AI handles volume, humans handle consequence.

A HOLD lands here with everything a reviewer needs to decide in seconds:
the request, the answer, the evidence, and exactly what failed.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ReviewItem:
    review_id: str
    request_id: str
    prompt: str
    answer: str
    reason: str
    findings: list[dict]
    proposed_action: dict | None
    created_at: float = field(default_factory=time.time)
    status: str = "PENDING"                 # PENDING | APPROVED | REJECTED | EDITED
    reviewer: str | None = None
    resolution_note: str | None = None
    edited_answer: str | None = None
    resolved_at: float | None = None


class HumanReviewQueue:
    def __init__(self) -> None:
        self._items: dict[str, ReviewItem] = {}
        self._lock = threading.Lock()
        self._notifier: Callable[[ReviewItem], None] | None = None

    def set_notifier(self, fn: Callable[[ReviewItem], None]) -> None:
        """TODO[FILL]: wire this to Slack, PagerDuty or email so reviewers are
        actually paged. Without it, items still queue but nobody is told.

            queue.set_notifier(lambda item: slack.post(
                channel="#controlplane-review",
                text=f"HOLD {item.review_id}: {item.reason}"))
        """
        self._notifier = fn

    def submit(self, request_id: str, prompt: str, answer: str, reason: str,
               findings: list[dict], proposed_action: dict | None = None) -> ReviewItem:
        item = ReviewItem(
            review_id=uuid.uuid4().hex[:10], request_id=request_id, prompt=prompt,
            answer=answer, reason=reason, findings=findings,
            proposed_action=proposed_action)
        with self._lock:
            self._items[item.review_id] = item
        if self._notifier:
            try:
                self._notifier(item)
            except Exception:
                pass          # never let a notification failure break the pipeline
        return item

    def pending(self) -> list[ReviewItem]:
        return [i for i in self._items.values() if i.status == "PENDING"]

    def get(self, review_id: str) -> ReviewItem | None:
        return self._items.get(review_id)

    def resolve(self, review_id: str, status: str, reviewer: str,
                note: str = "", edited_answer: str | None = None) -> ReviewItem:
        if status not in ("APPROVED", "REJECTED", "EDITED"):
            raise ValueError("status must be APPROVED, REJECTED or EDITED")
        with self._lock:
            item = self._items[review_id]
            item.status = status
            item.reviewer = reviewer
            item.resolution_note = note
            item.edited_answer = edited_answer
            item.resolved_at = time.time()
        return item

    def stats(self) -> dict[str, Any]:
        by = {}
        for i in self._items.values():
            by[i.status] = by.get(i.status, 0) + 1
        return {"total": len(self._items), "by_status": by}


review_queue = HumanReviewQueue()
