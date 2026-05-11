"""Simulated-day counter for the retailer app."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import SimState


class SimStateService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_current_day(self) -> int:
        """Return the current simulated day (0 if not initialised)."""
        row = self._db.query(SimState).filter_by(key="current_day").one_or_none()
        return int(row.value) if row is not None else 0

    def set_current_day(self, day: int) -> None:
        """Persist a new current-day value without committing."""
        row = self._db.query(SimState).filter_by(key="current_day").one_or_none()
        if row is None:
            self._db.add(SimState(key="current_day", value=str(day)))
        else:
            row.value = str(day)
