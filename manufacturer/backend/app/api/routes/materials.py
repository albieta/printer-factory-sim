from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from typing import List

from app.utils.database import get_db
from app.schemas.schemas import Material, MaterialCreate, BOMEntry, BOMCreate
from app.models.models import Product, ProductType, BillOfMaterials

router = APIRouter()


@router.get("/", response_model=List[Material])
def get_materials(db: Session = Depends(get_db)):
    materials = db.query(Product).filter(Product.type == ProductType.MATERIAL).all()
    return materials


@router.post("/", response_model=Material)
def create_material(material: MaterialCreate, db: Session = Depends(get_db)):
    new_material = Product(
        name=material.name,
        type=ProductType.MATERIAL
    )
    db.add(new_material)
    db.commit()
    db.refresh(new_material)
    return new_material


@router.get("/bom", response_model=List[BOMEntry])
def get_bom(db: Session = Depends(get_db)):
    return db.query(BillOfMaterials).all()


@router.post("/bom", response_model=BOMEntry)
def create_bom(bom: BOMCreate, db: Session = Depends(get_db)):
    # Validate finished product exists and is a PRINTER
    finished_product = db.query(Product).filter(Product.id == bom.finished_product_id).first()
    if not finished_product or finished_product.type != ProductType.PRINTER:
        raise HTTPException(status_code=400, detail="Finished product must be a printer")
    
    # Validate material exists and is a MATERIAL
    material = db.query(Product).filter(Product.id == bom.material_id).first()
    if not material or material.type != ProductType.MATERIAL:
        raise HTTPException(status_code=400, detail="Material must be a material product")
    
    new_bom = BillOfMaterials(**bom.model_dump())
    db.add(new_bom)
    db.commit()
    db.refresh(new_bom)
    return new_bom


@router.delete("/bom/{bom_id}")
def delete_bom(bom_id: str, db: Session = Depends(get_db)):
    bom = db.query(BillOfMaterials).filter(BillOfMaterials.id == bom_id).first()
    if not bom:
        raise HTTPException(status_code=404, detail="BOM entry not found")
    
    db.delete(bom)
    db.commit()
    return Response(status_code=204)
