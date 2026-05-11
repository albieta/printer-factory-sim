"""Append-only audit log for the retailer app.

Every meaningful state change — order placed, stock received, day
advanced — writes a row into the `events` table inside the same
transaction that performs the change. Callers must not commit between
the state change and the event row.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.models import Event, EventType


class EventService:
    """Thin wrapper that appends rows to the `events` table.

    Does not commit; the caller owns the transaction.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def record(
        self,
        event_type: EventType,
        sim_day: int,
        *,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> Event:
        """Append one event row and return the unflushed instance."""
        event = Event(
            event_type=event_type,
            sim_day=sim_day,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )
        self._db.add(event)
        return event
