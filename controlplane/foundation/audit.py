"""CONTROLPLANE FOUNDATION -> audit and decision log.

Every request produces exactly one ControlEvent. This is both the compliance
artefact and the training signal for the learning loop.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from config.settings import settings
from controlplane.types import ControlEvent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS control_events (
    request_id       TEXT PRIMARY KEY,
    created_at       REAL NOT NULL,
    actor_id         TEXT,
    decision         TEXT NOT NULL,
    reason           TEXT,
    model_id         TEXT,
    total_cost_usd   REAL,
    control_cost_usd REAL,
    total_latency_ms INTEGER,
    attempts         INTEGER,
    payload          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_decision ON control_events(decision);
CREATE INDEX IF NOT EXISTS idx_events_created  ON control_events(created_at);
"""


class AuditLog:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or settings.audit_db_path
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def write(self, event: ControlEvent) -> None:
        payload = json.dumps(event.to_dict(), default=str)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO control_events VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    event.request_id, event.created_at, event.actor_id,
                    event.decision, event.reason,
                    (event.generation or {}).get("model_id"),
                    event.total_cost_usd, event.control_cost_usd,
                    event.total_latency_ms, event.attempts, payload,
                ),
            )
            self._conn.commit()

    def get(self, request_id: str) -> dict[str, Any] | None:
        cur = self._conn.execute(
            "SELECT payload FROM control_events WHERE request_id = ?", (request_id,))
        row = cur.fetchone()
        return json.loads(row[0]) if row else None

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT payload FROM control_events ORDER BY created_at DESC LIMIT ?", (limit,))
        return [json.loads(r[0]) for r in cur.fetchall()]

    def stats(self) -> dict[str, Any]:
        cur = self._conn.execute(
            "SELECT decision, COUNT(*), COALESCE(SUM(total_cost_usd),0), "
            "COALESCE(AVG(total_latency_ms),0) FROM control_events GROUP BY decision")
        by_decision = {
            d: {"count": c, "cost_usd": round(s, 6), "avg_latency_ms": round(l, 1)}
            for d, c, s, l in cur.fetchall()
        }
        total = sum(v["count"] for v in by_decision.values())
        return {"total_requests": total, "by_decision": by_decision}


audit_log = AuditLog()
