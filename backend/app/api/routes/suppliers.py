from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import List

from app.utils.database import get_db
from app.schemas.schemas import Supplier, SupplierCreate, SupplierUpdate

router = APIRouter()


@router.get("/", response_model=List[Supplier])
def get_suppliers(db: Session = Depends(get_db)):
    from app.models.models import Supplier as SupplierModel
    return db.query(SupplierModel).all()


@router.post("/", response_model=Supplier)
def create_supplier(supplier: SupplierCreate, db: Session = Depends(get_db)):
    from app.models.models import Supplier as SupplierModel
    new_supplier = SupplierModel(**supplier.model_dump())
    db.add(new_supplier)
    db.commit()
    db.refresh(new_supplier)
    return new_supplier


@router.put("/{supplier_id}", response_model=Supplier)
def update_supplier(supplier_id: str, update: SupplierUpdate, db: Session = Depends(get_db)):
    from app.models.models import Supplier as SupplierModel
    from app.services.supplier_service import SupplierService
    
    service = SupplierService(db)
    try:
        return service.update_supplier(supplier_id, update)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{supplier_id}")
def delete_supplier(supplier_id: str, db: Session = Depends(get_db)):
    from app.models.models import Supplier as SupplierModel
    from app.services.supplier_service import SupplierService
    
    service = SupplierService(db)
    if not service.delete_supplier(supplier_id):
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    return Response(status_code=204)
