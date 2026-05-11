"""Config loader for the retailer app.

Reads a JSON file of the shape documented in `docs/PRD-week7.md` §4.2.
All paths resolved relative to the config file's parent directory so the
retailer can be launched from any working directory — the multi-instance
design requirement.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, field_validator


class ManufacturerRef(BaseModel):
    """Connection details for the upstream manufacturer API."""

    name: str
    url: str


class RetailerConfig(BaseModel):
    """Validated, resolved configuration for one retailer instance."""

    name: str
    port: int = 8003
    db_path: str
    manufacturer: ManufacturerRef
    markup_pct: float = 30.0

    @field_validator("markup_pct")
    @classmethod
    def markup_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("markup_pct must be positive")
        return v

    @field_validator("port")
    @classmethod
    def port_in_range(cls, v: int) -> int:
        if not (1024 <= v <= 65535):
            raise ValueError("port must be in [1024, 65535]")
        return v


def load_config(path: Path) -> RetailerConfig:
    """Parse a retailer JSON config file into a validated `RetailerConfig`.

    Relative `db_path` values are resolved against the config file's parent
    directory so two config files in different directories produce databases
    in their own directories without extra ceremony.
    """
    raw = json.loads(path.read_text())
    cfg = RetailerConfig(**raw["retailer"])

    # Resolve relative db_path against the config file's parent.
    db = Path(cfg.db_path)
    if not db.is_absolute():
        db = (path.parent / db).resolve()
    cfg = cfg.model_copy(update={"db_path": str(db)})
    return cfg
