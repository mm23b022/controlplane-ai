"""Central configuration. Reads config/*.yaml and environment variables."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent
ROOT_DIR = CONFIG_DIR.parent


@lru_cache(maxsize=None)
def load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache(maxsize=None)
def models_config() -> dict:
    return load_yaml("models.yaml")


@lru_cache(maxsize=None)
def policies() -> dict:
    return load_yaml("policies.yaml")


class Settings:
    # Which provider backs generation when no key is configured.
    default_provider: str = os.getenv("CP_DEFAULT_PROVIDER", "mock")
    audit_db_path: str = os.getenv("CP_AUDIT_DB", str(ROOT_DIR / "controlplane_audit.db"))
    cache_ttl_seconds: int = int(os.getenv("CP_CACHE_TTL", "300"))
    max_regeneration_attempts: int = int(os.getenv("CP_MAX_ATTEMPTS", "2"))

    # TODO[FILL]: provider credentials. Copy .env.example to .env and fill these.
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")


settings = Settings()
