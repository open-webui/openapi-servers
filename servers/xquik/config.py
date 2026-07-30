from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

API_CONTRACT = "2026-04-29"
UPSTREAM_API_ROOT = "https://xquik.com/api/v1"
UPSTREAM_SCHEMA_URL = "https://xquik.com/openapi.json"


@dataclass(frozen=True)
class Settings:
    api_key: str
    actions_enabled: bool


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    values = os.environ if environ is None else environ
    return Settings(
        api_key=values.get("XQUIK_API_KEY", "").strip(),
        actions_enabled=values.get("XQUIK_ENABLE_ACTIONS", "").lower() == "true",
    )
