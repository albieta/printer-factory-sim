"""Append-only audit log for the retailer app.

Every meaningful state change in the retailer — customer order
placement, backorder, fulfilment, purchase order, day advance, stock
movement — writes a row into the `events` table inside the same
SQLAlchemy transaction that performs the state change. This is the same
discipline `provider/app/services/event_service.py` enforces and the
PRD-week7 §3 audit-trail rule requires.

The service does not commit; the caller flushes/commits so the event
row stays in the same transaction as the state change it documents.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.models import Event, EventType


class EventService:
    """Thin wrapper that appends rows to the `events` table."""

    def __init__(self, db: Session) -> None:
        self.db = db

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
        self.db.add(event)
        return event

    def list(
        self,
        *,
        event_type: Optional[EventType] = None,
        from_day: Optional[int] = None,
        to_day: Optional[int] = None,
        limit: int = 100,
    ) -> list[Event]:
        """Return events ordered newest-first, with optional filters."""

        query = self.db.query(Event)
        if event_type is not None:
            query = query.filter(Event.event_type == event_type)
        if from_day is not None:
            query = query.filter(Event.sim_day >= from_day)
        if to_day is not None:
            query = query.filter(Event.sim_day <= to_day)
        return query.order_by(Event.id.desc()).limit(limit).all()
