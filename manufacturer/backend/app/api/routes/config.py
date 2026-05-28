from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import List

from app.models.models import Product, ProductType
from app.schemas.schemas import PrinterModel, PrinterModelCreate, SimulationConfig, SimulationConfigUpdate
from app.services.config_service import ConfigService
from app.services.financial_service import FinancialService
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


@router.post("/assembly/open-line", response_model=SimulationConfig)
def open_assembly_line(db: Session = Depends(get_db)):
    config_service = ConfigService(db)
    financial_service = FinancialService(db)
    config = config_service.get_config()
    new_lines = config.assembly_lines + 1
    config_service.update_config(SimulationConfigUpdate(assembly_lines=new_lines))
    financial_service.record_assembly_line_opened(config.sim_day)
    return config_service.serialize_config()


@router.post("/assembly/hire-worker", response_model=SimulationConfig)
def hire_worker(db: Session = Depends(get_db)):
    config_service = ConfigService(db)
    financial_service = FinancialService(db)
    config = config_service.get_config()
    if config.workers_per_line >= config.max_workers_per_line:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot hire more workers. Max workers per line is {config.max_workers_per_line}"
        )
    new_workers = config.workers_per_line + 1
    config_service.update_config(SimulationConfigUpdate(workers_per_line=new_workers))
    financial_service.record_worker_hired(config.sim_day)
    return config_service.serialize_config()


@router.post("/assembly/fire-worker", response_model=SimulationConfig)
def fire_worker(db: Session = Depends(get_db)):
    config_service = ConfigService(db)
    financial_service = FinancialService(db)
    config = config_service.get_config()

    if config.workers_per_line <= 1:
        raise HTTPException(
            status_code=400,
            detail="Cannot fire workers. Minimum of 1 worker per line required."
        )

    new_workers = config.workers_per_line - 1
    config_service.update_config(SimulationConfigUpdate(workers_per_line=new_workers))
    financial_service.record_worker_fired(config.sim_day)
    return config_service.serialize_config()


@router.post("/assembly/close-line", response_model=SimulationConfig)
def close_assembly_line(db: Session = Depends(get_db)):
    config_service = ConfigService(db)
    financial_service = FinancialService(db)
    config = config_service.get_config()

    if config.assembly_lines <= 1:
        raise HTTPException(
            status_code=400,
            detail="Cannot close assembly lines. Minimum of 1 line required."
        )

    new_lines = config.assembly_lines - 1
    config_service.update_config(SimulationConfigUpdate(assembly_lines=new_lines))
    financial_service.record_assembly_line_closed(config.sim_day)
    return config_service.serialize_config()


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


@router.post("/apply-scenario-assembly", response_model=SimulationConfig)
def apply_scenario_assembly(assembly: dict, db: Session = Depends(get_db)):
    """Apply recommended assembly configuration from a scenario."""
    config_service = ConfigService(db)
    update_data = {
        k: v for k, v in assembly.items()
        if k in ["assembly_lines", "workers_per_line", "shift_hours"]
    }
    if not update_data:
        return config_service.serialize_config()

    config_service.update_config(SimulationConfigUpdate(**update_data))
    return config_service.serialize_config()


@router.post("/apply-scenario-costs", response_model=SimulationConfig)
def apply_scenario_costs(costs: dict, db: Session = Depends(get_db)):
    """Apply recommended cost configuration from a scenario."""
    config_service = ConfigService(db)
    update_data = {
        k: v for k, v in costs.items()
        if k in ["cost_per_assembly_line", "cost_per_assembly_line_per_day", "cost_per_worker_per_hour", "max_workers_per_line"]
    }
    if not update_data:
        return config_service.serialize_config()

    config_service.update_config(SimulationConfigUpdate(**update_data))
    return config_service.serialize_config()


@router.post("/init-prices", response_model=dict)
def init_prices(db: Session = Depends(get_db)):
    """Ensure wholesale prices are initialized for all printer models."""
    from app.services.wholesale_price_service import WholesalePriceService

    service = WholesalePriceService(db)
    service.ensure_defaults()
    db.commit()
    prices = service.list_prices()
    return {
        "initialized": True,
        "prices": {name: str(p) for name, p in prices.items()}
    }
