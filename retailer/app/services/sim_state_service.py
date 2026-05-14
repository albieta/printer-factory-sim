"""Read/write the retailer's simulated-day counter.

The retailer stores its simulated time as a single row in the
`sim_state` key/value table (`key='current_day'`). Each app owns its own
day counter and the turn engine (PRD-week7 §6) is the only entity
allowed to advance the day once the engine is in use.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.models import SimState
from app.services.starter_profile import INITIAL_DAY


CURRENT_DAY_KEY = "current_day"


class SimStateService:
    """CRUD for the simulated-day counter."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_current_day(self) -> int:
        """Return the retailer's current simulated day.

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
