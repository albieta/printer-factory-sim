from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import List

from app.models.models import Product, ProductType
from app.schemas.schemas import PrinterModel, PrinterModelCreate, SimulationConfig, SimulationConfigUpdate
from app.services.config_service import ConfigService
from app.utils.database import get_db

router = APIRouter()


@router.get("/", response_model=SimulationConfig)
def get_config(db: Session = Depends(get_db)):
    return ConfigService(db).serialize_config()


@router.put("/", response_model=SimulationConfig)
def update_config(config_update: SimulationConfigUpdate, db: Session = Depends(get_db)):
    service = ConfigService(db)
    service.update_config(config_update)
    return service.serialize_config()


@router.get("/printer-models", response_model=List[PrinterModel])
def get_printer_models(db: Session = Depends(get_db)):
    return db.query(Product).filter(Product.type == ProductType.PRINTER).all()


@router.post("/printer-models", response_model=PrinterModel)
def create_printer_model(printer: PrinterModelCreate, db: Session = Depends(get_db)):
    new_printer = Product(name=printer.name, type=ProductType.PRINTER, assembly_hours=printer.assembly_hours)
    db.add(new_printer)
    db.commit()
    db.refresh(new_printer)
    return new_printer


@router.delete("/printer-models/{printer_id}")
def delete_printer_model(printer_id: str, db: Session = Depends(get_db)):
    printer = db.query(Product).filter(Product.id == printer_id).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer model not found")

    db.delete(printer)
    db.commit()
    return Response(status_code=204)
