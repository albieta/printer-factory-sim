from sqlalchemy.orm import Session
from app.models.models import SimulationConfig
from app.schemas.schemas import SimulationConfigUpdate
from datetime import date


class ConfigService:
    def __init__(self, db: Session):
        self.db = db

    def get_config(self) -> SimulationConfig:
        config = self.db.query(SimulationConfig).first()
        if not config:
            config = SimulationConfig()
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)
        return config

    def update_config(self, config_update: SimulationConfigUpdate) -> SimulationConfig:
        config = self.get_config()
        for key, value in config_update.model_dump(exclude_unset=True).items():
            setattr(config, key, value)
        self.db.commit()
        self.db.refresh(config)
        return config

    def get_sim_date(self) -> date:
        config = self.get_config()
        return config.sim_date

    def advance_sim_date(self) -> date:
        config = self.get_config()
        from datetime import timedelta
        config.sim_date += timedelta(days=1)
        self.db.commit()
        self.db.refresh(config)
        return config.sim_date

    def get_warehouse_capacity(self) -> int:
        config = self.get_config()
        return config.warehouse_capacity

    def get_daily_assembly_hours(self) -> float:
        config = self.get_config()
        return config.daily_assembly_hours
