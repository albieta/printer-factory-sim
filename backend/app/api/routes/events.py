from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date

from app.utils.database import get_db
from app.schemas.schemas import Event, TimeSeriesData

router = APIRouter()


@router.get("/", response_model=List[Event])
def get_events(
    type: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: Session = Depends(get_db)
):
    from app.services.event_service import EventService
    from app.models.models import EventType
    
    service = EventService(db)
    
    event_type = None
    if type:
        try:
            event_type = EventType(type)
        except ValueError:
            pass
    
    return service.get_events(event_type, from_date, to_date)


@router.get("/timeseries/{metric}", response_model=TimeSeriesData)
def get_timeseries(
    metric: str,
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: Session = Depends(get_db)
):
    from app.services.event_service import EventService
    
    service = EventService(db)
    data_points = service.get_timeseries_data(metric, from_date, to_date)
    
    return TimeSeriesData(metric=metric, data_points=data_points)
