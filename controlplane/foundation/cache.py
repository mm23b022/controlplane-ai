"""CONTROLPLANE FOUNDATION -> cache.

Rule from the strategy: cache only what is safe to reuse. Never cache anything
that depends on user permissions, account state, or real-time risk.
"""
from __future__ import annotations

import time
from typing import Any

from config.settings import settings

_UNSAFE_KEYS = ("permission", "balance", "account_state", "risk", "actor")


class TTLCache:
    def __init__(self, ttl: int | None = None) -> None:
        self.ttl = ttl or settings.cache_ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}
        self.hits = 0
        self.misses = 0

    @staticmethod
    def is_cacheable(key: str) -> bool:
        low = key.lower()
        return not any(u in low for u in _UNSAFE_KEYS)

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if not entry:
            self.misses += 1
            return None
        expires, value = entry
        if time.time() > expires:
            self._store.pop(key, None)
            self.misses += 1
            return None
        self.hits += 1
        return value

    def set(self, key: str, value: Any) -> None:
        if not self.is_cacheable(key):
            return
        self._store[key] = (time.time() + self.ttl, value)

    def clear(self) -> None:
        self._store.clear()


policy_cache = TTLCache()
