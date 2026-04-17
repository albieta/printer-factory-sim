from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import List

from app.schemas.schemas import Supplier, SupplierCreate, SupplierUpdate
from app.services.supplier_service import SupplierService
from app.utils.database import get_db

router = APIRouter()


@router.get("/", response_model=List[Supplier])
def get_suppliers(db: Session = Depends(get_db)):
    service = SupplierService(db)
    return [service.serialize_supplier(supplier) for supplier in service.get_all_suppliers()]


@router.post("/", response_model=Supplier)
def create_supplier(supplier: SupplierCreate, db: Session = Depends(get_db)):
    service = SupplierService(db)
    created = service.create_supplier(supplier)
    return service.serialize_supplier(created)


@router.put("/{supplier_id}", response_model=Supplier)
def update_supplier(supplier_id: str, update: SupplierUpdate, db: Session = Depends(get_db)):
    service = SupplierService(db)
    try:
        updated = service.update_supplier(supplier_id, update)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return service.serialize_supplier(updated)


@router.delete("/{supplier_id}")
def delete_supplier(supplier_id: str, db: Session = Depends(get_db)):
    service = SupplierService(db)
    if not service.delete_supplier(supplier_id):
        raise HTTPException(status_code=404, detail="Supplier not found")
    return Response(status_code=204)
