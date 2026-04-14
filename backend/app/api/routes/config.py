from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import List

from app.utils.database import get_db
from app.schemas.schemas import (
    SimulationConfig, SimulationConfigUpdate,
    PrinterModel, PrinterModelCreate
)
from app.models.models import Product, ProductType
from app.services.config_service import ConfigService

router = APIRouter()


@router.get("/", response_model=SimulationConfig)
def get_config(db: Session = Depends(get_db)):
    config_service = ConfigService(db)
    return config_service.get_config()


@router.put("/", response_model=SimulationConfig)
def update_config(config_update: SimulationConfigUpdate, db: Session = Depends(get_db)):
    config_service = ConfigService(db)
    return config_service.update_config(config_update)


@router.get("/printer-models", response_model=List[PrinterModel])
def get_printer_models(db: Session = Depends(get_db)):
    printers = db.query(Product).filter(Product.type == ProductType.PRINTER).all()
    return printers


@router.post("/printer-models", response_model=PrinterModel)
def create_printer_model(printer: PrinterModelCreate, db: Session = Depends(get_db)):
    new_printer = Product(
        name=printer.name,
        type=ProductType.PRINTER,
        assembly_hours=printer.assembly_hours
    )
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
