from sqlalchemy.orm import Session
from app.models.models import Event, EventType
from datetime import date
from typing import Any, List, Optional


class EventService:
    def __init__(self, db: Session):
        self.db = db

    def get_events(
        self, 
        event_type: Optional[EventType] = None, 
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        limit: int = 100
    ) -> List[Event]:
        query = self.db.query(Event)
        
        if event_type:
            query = query.filter(Event.event_type == event_type)
        if from_date:
            query = query.filter(Event.sim_date >= from_date)
        if to_date:
            query = query.filter(Event.sim_date <= to_date)
        
        query = query.order_by(Event.timestamp.desc())
        return query.limit(limit).all()

    def get_timeseries_data(self, metric: str, from_date: Optional[date] = None, to_date: Optional[date] = None) -> list[dict[str, Any]]:
        """Get time series data for charting"""
        query = self.db.query(Event)
        
        if from_date:
            query = query.filter(Event.sim_date >= from_date)
        if to_date:
            query = query.filter(Event.sim_date <= to_date)
        
        events = query.order_by(Event.sim_date).all()
        
        # Aggregate by metric type
        data_points = []
        for event in events:
            if metric == "all" or event.event_type.value.startswith(metric.upper()):
                data_points.append({
                    "date": event.sim_date.isoformat(),
                    "event_type": event.event_type.value,
                    "details": event.details
                })
        
        return data_points
