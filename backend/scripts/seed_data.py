#!/usr/bin/env python3
"""
Seed data script for 3D Printer Production Simulator
Initializes the database with sample configuration and data
"""

import sys
import os
from datetime import date

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.database import SessionLocal, engine, Base
from app.models.models import (
    Product, ProductType, BillOfMaterials, Supplier,
    Inventory, SimulationConfig
)


def seed_database():
    """Populate database with initial seed data"""
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    try:
        # Check if data already exists
        existing_config = db.query(SimulationConfig).first()
        if existing_config:
            print("Database already seeded. Skipping...")
            return
        
        print("Seeding database...")
        
        # 1. Create simulation config
        config = SimulationConfig(
            warehouse_capacity=1000,
            daily_assembly_hours=8.0,
            demand_distribution_mean=5.0,
            demand_distribution_variance=2.0,
            sim_date=date.today()
        )
        db.add(config)
        db.commit()
        print("✓ Created simulation config")
        
        # 2. Create printer models
        basic300 = Product(name="Basic300", type=ProductType.PRINTER, assembly_hours=2.0)
        pro450 = Product(name="Pro450", type=ProductType.PRINTER, assembly_hours=4.0)
        elite700 = Product(name="Elite700", type=ProductType.PRINTER, assembly_hours=6.0)
        
        db.add_all([basic300, pro450, elite700])
        db.commit()
        print("✓ Created 3 printer models")
        
        # 3. Create materials
        pla_filament = Product(name="PLA Filament", type=ProductType.MATERIAL)
        abs_filament = Product(name="ABS Filament", type=ProductType.MATERIAL)
        aluminum_frame = Product(name="Aluminum Frame", type=ProductType.MATERIAL)
        stepper_motor = Product(name="Stepper Motor", type=ProductType.MATERIAL)
        control_board = Product(name="Control Board", type=ProductType.MATERIAL)
        lcd_screen = Product(name="LCD Screen", type=ProductType.MATERIAL)
        
        db.add_all([pla_filament, abs_filament, aluminum_frame, stepper_motor, control_board, lcd_screen])
        db.commit()
        print("✓ Created 6 materials")
        
        # 4. Create BOM entries
        # Basic300 BOM
        bom1 = BillOfMaterials(finished_product_id=basic300.id, material_id=pla_filament.id, quantity=2.5)
        bom2 = BillOfMaterials(finished_product_id=basic300.id, material_id=aluminum_frame.id, quantity=1.0)
        bom3 = BillOfMaterials(finished_product_id=basic300.id, material_id=stepper_motor.id, quantity=3.0)
        bom4 = BillOfMaterials(finished_product_id=basic300.id, material_id=control_board.id, quantity=1.0)
        
        # Pro450 BOM
        bom5 = BillOfMaterials(finished_product_id=pro450.id, material_id=abs_filament.id, quantity=4.0)
        bom6 = BillOfMaterials(finished_product_id=pro450.id, material_id=aluminum_frame.id, quantity=2.0)
        bom7 = BillOfMaterials(finished_product_id=pro450.id, material_id=stepper_motor.id, quantity=4.0)
        bom8 = BillOfMaterials(finished_product_id=pro450.id, material_id=control_board.id, quantity=2.0)
        
        # Elite700 BOM
        bom9 = BillOfMaterials(finished_product_id=elite700.id, material_id=abs_filament.id, quantity=6.0)
        bom10 = BillOfMaterials(finished_product_id=elite700.id, material_id=aluminum_frame.id, quantity=3.0)
        bom11 = BillOfMaterials(finished_product_id=elite700.id, material_id=stepper_motor.id, quantity=6.0)
        bom12 = BillOfMaterials(finished_product_id=elite700.id, material_id=control_board.id, quantity=2.0)
        bom13 = BillOfMaterials(finished_product_id=elite700.id, material_id=lcd_screen.id, quantity=1.0)
        
        db.add_all([bom1, bom2, bom3, bom4, bom5, bom6, bom7, bom8, bom9, bom10, bom11, bom12, bom13])
        db.commit()
        print("✓ Created 13 BOM entries")
        
        # 5. Create suppliers
        supplier1 = Supplier(
            name="FilamentPro Inc.",
            product_id=pla_filament.id,
            unit_cost=25.00,
            lead_time_days=5,
            quantity_breaks=[
                {"qty": 100, "price": 22.50},
                {"qty": 500, "price": 20.00}
            ]
        )
        
        supplier2 = Supplier(
            name="ABS Materials Ltd.",
            product_id=abs_filament.id,
            unit_cost=30.00,
            lead_time_days=7,
            quantity_breaks=[
                {"qty": 150, "price": 27.00},
                {"qty": 600, "price": 24.00}
            ]
        )
        
        supplier3 = Supplier(
            name="MetalWorks Supply",
            product_id=aluminum_frame.id,
            unit_cost=45.00,
            lead_time_days=10,
            quantity_breaks=[
                {"qty": 50, "price": 42.00},
                {"qty": 200, "price": 38.00}
            ]
        )
        
        supplier4 = Supplier(
            name="MotorTech Direct",
            product_id=stepper_motor.id,
            unit_cost=15.00,
            lead_time_days=14,
            quantity_breaks=[
                {"qty": 100, "price": 13.50},
                {"qty": 400, "price": 12.00}
            ]
        )
        
        supplier5 = Supplier(
            name="ElectroComponents",
            product_id=control_board.id,
            unit_cost=35.00,
            lead_time_days=12,
            quantity_breaks=[
                {"qty": 75, "price": 32.00},
                {"qty": 300, "price": 28.00}
            ]
        )
        
        supplier6 = Supplier(
            name="DisplayTech Solutions",
            product_id=lcd_screen.id,
            unit_cost=50.00,
            lead_time_days=15,
            quantity_breaks=[
                {"qty": 50, "price": 47.00},
                {"qty": 250, "price": 43.00}
            ]
        )
        
        db.add_all([supplier1, supplier2, supplier3, supplier4, supplier5, supplier6])
        db.commit()
        print("✓ Created 6 suppliers")
        
        # 6. Initialize inventory with starting stock
        inventory_items = [
            Inventory(product_id=pla_filament.id, quantity=500.0),
            Inventory(product_id=abs_filament.id, quantity=400.0),
            Inventory(product_id=aluminum_frame.id, quantity=200.0),
            Inventory(product_id=stepper_motor.id, quantity=300.0),
            Inventory(product_id=control_board.id, quantity=150.0),
            Inventory(product_id=lcd_screen.id, quantity=100.0)
        ]
        
        db.add_all(inventory_items)
        db.commit()
        print("✓ Initialized inventory with starting stock")
        
        print("\n✓ Database seeding completed successfully!")
        print(f"\nSimulation start date: {date.today()}")
        
    except Exception as e:
        db.rollback()
        print(f"✗ Error seeding database: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
