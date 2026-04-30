from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def manufacturer_root() -> Path:
    return Path(__file__).resolve().parents[3]


def config_path() -> Path:
    return manufacturer_root() / "config.json"


def load_app_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return {"manufacturer": {"providers": []}}

    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    manufacturer = payload.setdefault("manufacturer", {})
    manufacturer.setdefault("providers", [])
    return payload


def get_configured_providers() -> list[dict[str, Any]]:
    providers = load_app_config().get("manufacturer", {}).get("providers", [])
    if not isinstance(providers, list):
        raise ValueError("manufacturer.providers must be a list in manufacturer/config.json.")
    return providers


def get_manufacturer_port(default: int = 8002) -> int:
    value = load_app_config().get("manufacturer", {}).get("port", default)
    return int(value)
