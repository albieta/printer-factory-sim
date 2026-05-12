from __future__ import annotations
from typing import Any

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.models import SimulationConfig
from app.schemas.schemas import SimulationConfigUpdate
from app.services.starter_profile import build_starter_config, calculate_effective_daily_assembly_hours


class ConfigService:
    def __init__(self, db: Session):
        self.db = db

    def ensure_capacity_fields(self, config: SimulationConfig) -> SimulationConfig:
        if not config.assembly_lines:
            config.assembly_lines = 1
        if not config.workers_per_line:
            config.workers_per_line = 1
        if not config.shift_hours:
            config.shift_hours = config.daily_assembly_hours or 8.0

        config.daily_assembly_hours = calculate_effective_daily_assembly_hours(
            config.assembly_lines,
            config.workers_per_line,
            config.shift_hours,
        )
        return config

    def get_config(self) -> SimulationConfig:
        config = self.db.query(SimulationConfig).first()
        if not config:
            config = SimulationConfig(**build_starter_config())
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)

        self.ensure_capacity_fields(config)
        self.db.commit()
        self.db.refresh(config)
        return config

    def get_effective_daily_assembly_hours(self, config: SimulationConfig | None = None) -> float:
        target = config or self.get_config()
        self.ensure_capacity_fields(target)
        return float(target.daily_assembly_hours)

    def update_config(self, config_update: SimulationConfigUpdate) -> SimulationConfig:
        config = self.get_config()
        payload = config_update.model_dump(exclude_unset=True)

        for key, value in payload.items():
            setattr(config, key, value)

        config.assembly_lines = max(1, int(config.assembly_lines))
        config.workers_per_line = max(1, int(config.workers_per_line))

        if "daily_assembly_hours" in payload and not any(key in payload for key in ("assembly_lines", "workers_per_line", "shift_hours")):
            denominator = max(1, config.assembly_lines * config.workers_per_line)
            config.shift_hours = float(payload["daily_assembly_hours"]) / denominator

        self.ensure_capacity_fields(config)
        self.db.commit()
        self.db.refresh(config)
        return config

    def serialize_config(self) -> dict[str, Any]:
        config = self.get_config()
        return {
            "id": config.id,
            "warehouse_capacity": config.warehouse_capacity,
            "daily_assembly_hours": config.daily_assembly_hours,
            "assembly_lines": config.assembly_lines,
            "workers_per_line": config.workers_per_line,
            "shift_hours": config.shift_hours,
            "effective_daily_assembly_hours": self.get_effective_daily_assembly_hours(config),
            "demand_distribution_mean": config.demand_distribution_mean,
            "demand_distribution_variance": config.demand_distribution_variance,
            "sim_date": config.sim_date,
        }

    def get_sim_date(self) -> date:
        return self.get_config().sim_date

    def advance_sim_date(self) -> date:
        config = self.get_config()
        config.sim_date += timedelta(days=1)
        self.db.commit()
        self.db.refresh(config)
        return config.sim_date

    def get_warehouse_capacity(self) -> int:
        return self.get_config().warehouse_capacity

    def get_daily_assembly_hours(self) -> float:
        return self.get_effective_daily_assembly_hours()
