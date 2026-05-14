from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.schemas import Event, EventType
from app.models.models import EventType as ModelEventType
from app.services.event_service import EventService
from app.utils.database import get_db

router = APIRouter()


@router.get("", response_model=list[Event])
def list_events(
    event_type: Optional[EventType] = None,
    from_day: Optional[int] = None,
    to_day: Optional[int] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[Event]:
    model_type = ModelEventType(event_type.value) if event_type is not None else None
    events = EventService(db).list(
        event_type=model_type,
        from_day=from_day,
        to_day=to_day,
        limit=limit,
    )
    return [Event.model_validate(e) for e in events]
