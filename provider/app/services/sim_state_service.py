"""Read/write the provider's simulated-day counter.

The provider stores its simulated time as a single row in the
`sim_state` key/value table (`key='current_day'`). Each app owns its own
day counter — the manufacturer keeps its own value in
`simulation_config.sim_date` — and the human operator advances them
manually, provider first, every day.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import SimState
from app.services.starter_profile import INITIAL_DAY


CURRENT_DAY_KEY = "current_day"
LEAD_TIME_MODIFIER_KEY = "lead_time_modifier"
SUPPLY_MODIFIER_KEY = "supply_modifier"


class SimStateService:
    """CRUD for the simulated-day counter."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_current_day(self) -> int:
        """Return the provider's current simulated day.

        Falls back to `INITIAL_DAY` and inserts the row if the table is
        empty, so a freshly-bootstrapped database that skipped the seed
        loader still has a usable counter.
        """

        row = self.db.query(SimState).filter_by(key=CURRENT_DAY_KEY).one_or_none()
        if row is None:
            row = SimState(key=CURRENT_DAY_KEY, value=str(INITIAL_DAY))
            self.db.add(row)
            self.db.flush()
            return INITIAL_DAY
        return int(row.value)

    def set_current_day(self, day: int) -> None:
        """Persist `day` as the new simulated day."""

        row = self.db.query(SimState).filter_by(key=CURRENT_DAY_KEY).one_or_none()
        if row is None:
            row = SimState(key=CURRENT_DAY_KEY, value=str(day))
            self.db.add(row)
        else:
            row.value = str(day)

    def get_float(self, key: str, default: float) -> float:
        """Return a float simulator setting from the key/value table."""

        row = self.db.query(SimState).filter_by(key=key).one_or_none()
        if row is None:
            return default
        try:
            return float(row.value)
        except ValueError:
            return default

    def set_value(self, key: str, value: str) -> None:
        """Persist a scalar simulator setting."""

        row = self.db.query(SimState).filter_by(key=key).one_or_none()
        if row is None:
            row = SimState(key=key, value=value)
            self.db.add(row)
        else:
            row.value = value

    def get_lead_time_modifier(self) -> float:
        """Return the active market lead-time multiplier."""

        return max(1.0, self.get_float(LEAD_TIME_MODIFIER_KEY, 1.0))

    def set_market_signal(self, *, supply_modifier: float, lead_time_modifier: float) -> None:
        """Store current market modifiers used by provider order intake."""

        self.set_value(SUPPLY_MODIFIER_KEY, str(supply_modifier))
        self.set_value(LEAD_TIME_MODIFIER_KEY, str(max(1.0, lead_time_modifier)))
