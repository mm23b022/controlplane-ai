"""CONTINUOUS LEARNING -- outcomes -> better routing -> better verification.

Implemented here: model reliability scoring from real outcomes, and false-alarm
tracking per detector. Both are read back by CAI on the next request.
"""
from __future__ import annotations

import json
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any

from config.settings import ROOT_DIR
from controlplane.types import ControlEvent, Decision

_STATE_PATH = Path(ROOT_DIR) / "controlplane_learning.json"


class LearningLoop:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _STATE_PATH
        self._lock = threading.Lock()
        self.model_stats: dict[str, dict[str, float]] = defaultdict(
            lambda: {"runs": 0, "clean": 0, "reworked": 0, "blocked": 0,
                     "cost": 0.0, "predicted_cost": 0.0})
        self.detector_stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"fired": 0, "confirmed": 0, "false_alarm": 0})
        self._load()

    # ------------------------------------------------------------------
    def record(self, event: ControlEvent) -> None:
        model_id = (event.generation or {}).get("model_id")
        if not model_id:
            return
        with self._lock:
            s = self.model_stats[model_id]
            s["runs"] += 1
            s["cost"] += event.total_cost_usd
            s["predicted_cost"] += (event.routing or {}).get("expected_cost_usd", 0.0)
            if event.decision == Decision.ALLOW.value:
                s["clean"] += 1
            elif event.decision in (Decision.REGENERATE.value, Decision.HOLD.value):
                s["reworked"] += 1
            elif event.decision == Decision.BLOCK.value:
                s["blocked"] += 1

            for check in event.checks or []:
                for f in check.get("findings", []):
                    self.detector_stats[f.get("category", "unknown")]["fired"] += 1
        self._save()

    def record_review(self, category: str, upheld: bool) -> None:
        """A human confirming or overturning a finding is the cleanest signal
        we get. Only *validated* feedback is allowed to move policy."""
        with self._lock:
            d = self.detector_stats[category]
            d["confirmed" if upheld else "false_alarm"] += 1
        self._save()

    # ------------------------------------------------------------------
    def reliability(self, model_id: str) -> float | None:
        """Observed clean-pass rate, used to adjust CAI's success estimate."""
        s = self.model_stats.get(model_id)
        if not s or s["runs"] < 5:
            return None                     # not enough evidence to move routing
        return round(s["clean"] / s["runs"], 4)

    def false_alarm_rate(self, category: str) -> float | None:
        d = self.detector_stats.get(category)
        if not d:
            return None
        total = d["confirmed"] + d["false_alarm"]
        if total < 5:
            return None
        return round(d["false_alarm"] / total, 4)

    def cost_accuracy(self, model_id: str) -> float | None:
        s = self.model_stats.get(model_id)
        if not s or not s["predicted_cost"]:
            return None
        return round(s["cost"] / s["predicted_cost"], 4)

    def retrain_router(self) -> dict[str, Any]:
        """TODO[FILL]: fold observed reliability back into config/models.yaml.

        Suggested approach:
          1. For each model, blend the declared `skills` score with the observed
             clean-pass rate per task type (e.g. 0.7 * declared + 0.3 * observed).
          2. Write the updated scores back to models.yaml, or to an override
             table the ModelRegistry reads at startup.
          3. Never let a single bad day rewrite a score -- require a minimum
             sample size and cap the per-cycle delta.
        """
        return {"status": "not_implemented",
                "models_tracked": len(self.model_stats)}

    # ------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        return {
            "models": {k: dict(v) for k, v in self.model_stats.items()},
            "detectors": {k: dict(v) for k, v in self.detector_stats.items()},
        }

    def _save(self) -> None:
        try:
            self.path.write_text(json.dumps(self.snapshot(), indent=2))
        except Exception:
            pass

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
        except Exception:
            return
        for k, v in (data.get("models") or {}).items():
            self.model_stats[k].update(v)
        for k, v in (data.get("detectors") or {}).items():
            self.detector_stats[k].update(v)


learning_loop = LearningLoop()
