from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy.orm import Session


def build_reference_code(prefix: str, target_date: date, sequence: int) -> str:
    return f"{prefix}-{target_date.strftime('%Y%m%d')}-{sequence:03d}"



def next_reference_code(
    db: Session,
    model: Any,
    prefix: str,
    date_field: str,
    target_date: date,
) -> str:
    date_attr = getattr(model, date_field)
    sequence = db.query(model).filter(date_attr == target_date).count() + 1
    return build_reference_code(prefix, target_date, sequence)



def backfill_references(db: Session, model: Any, prefix: str, date_field: str) -> None:
    items = db.query(model).order_by(getattr(model, date_field), model.id).all()
    sequence_by_date: dict[date, int] = defaultdict(int)

    for item in items:
        target_date = getattr(item, date_field)
        if not target_date:
            continue
        sequence_by_date[target_date] += 1
        if not getattr(item, "reference_code", None):
            item.reference_code = build_reference_code(prefix, target_date, sequence_by_date[target_date])
