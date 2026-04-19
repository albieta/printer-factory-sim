from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.api.routes.inventory import manual_adjust_inventory
from app.models.models import (
    BillOfMaterials,
    Event,
    EventType,
    Inventory,
    ManufacturingOrder,
    OrderStatus,
    Product,
    ProductType,
    PurchaseOrder,
    PurchaseOrderStatus,
    SimulationConfig,
    Supplier,
)
from app.schemas.schemas import ManualAdjust
from app.services.config_service import ConfigService
from app.services.inventory_service import InventoryService
from app.services.order_service import OrderService
from app.services.supplier_service import PurchaseOrderService
from app.utils.database import Base


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def seed_config(session, sim_date: date = date(2026, 4, 19)) -> SimulationConfig:
    config = SimulationConfig(
        warehouse_capacity=5000,
        assembly_lines=2,
        workers_per_line=3,
        shift_hours=8.0,
        daily_assembly_hours=40.0,
        demand_distribution_mean=5.0,
        demand_distribution_variance=2.0,
        sim_date=sim_date,
    )
    session.add(config)
    session.commit()
    return config


def create_material(session, name: str) -> Product:
    material = Product(name=name, type=ProductType.MATERIAL)
    session.add(material)
    session.commit()
    session.refresh(material)
    session.add(Inventory(product_id=material.id, quantity=Decimal("0"), last_updated=datetime.utcnow()))
    session.commit()
    return material


def create_printer(session, name: str = "FactoryPrinter", assembly_hours: float = 4.0) -> Product:
    printer = Product(name=name, type=ProductType.PRINTER, assembly_hours=assembly_hours)
    session.add(printer)
    session.commit()
    session.refresh(printer)
    return printer


def add_bom(session, printer: Product, material: Product, quantity: str) -> None:
    session.add(
        BillOfMaterials(
            finished_product_id=printer.id,
            material_id=material.id,
            quantity=Decimal(quantity),
        )
    )
    session.commit()


def create_order(
    session,
    printer: Product,
    quantity: int,
    status: OrderStatus,
    *,
    reference_code: str,
    sim_date: date,
) -> ManufacturingOrder:
    order = ManufacturingOrder(
        reference_code=reference_code,
        product_id=printer.id,
        quantity=quantity,
        status=status,
        created_date=sim_date,
        released_date=sim_date if status == OrderStatus.RELEASED else None,
        completed_date=sim_date if status == OrderStatus.COMPLETED else None,
        status_reason="Blocked by missing stock." if status == OrderStatus.BLOCKED else None,
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


def test_rejecting_a_pending_order_sets_terminal_status_and_blocks_release():
    session = make_session()
    try:
        sim_date = date(2026, 4, 19)
        seed_config(session, sim_date)
        printer = create_printer(session)
        order = OrderService(session).create_order(printer.id, 2, sim_date)

        reject_result = OrderService(session).reject_order(order.id, sim_date)
        session.refresh(order)

        assert reject_result["success"] is True
        assert order.status == OrderStatus.REJECTED

        release_result = OrderService(session).release_order(order.id, sim_date)
        assert release_result["success"] is False
        assert "not PENDING" in release_result["error"]

        event_types = [event.event_type for event in session.query(Event).all()]
        assert EventType.ORDER_REJECTED in event_types
    finally:
        session.close()


def test_accepted_order_material_demand_counts_only_released_and_blocked_orders():
    session = make_session()
    try:
        sim_date = date(2026, 4, 19)
        seed_config(session, sim_date)
        material = create_material(session, "PLA Filament")
        printer = create_printer(session)
        add_bom(session, printer, material, "2.0")

        create_order(session, printer, 3, OrderStatus.RELEASED, reference_code="MO-001", sim_date=sim_date)
        create_order(session, printer, 4, OrderStatus.BLOCKED, reference_code="MO-002", sim_date=sim_date)
        create_order(session, printer, 5, OrderStatus.PENDING, reference_code="MO-003", sim_date=sim_date)
        create_order(session, printer, 6, OrderStatus.REJECTED, reference_code="MO-004", sim_date=sim_date)
        create_order(session, printer, 7, OrderStatus.COMPLETED, reference_code="MO-005", sim_date=sim_date)

        demand_by_material = InventoryService(session).get_accepted_order_material_demand()

        assert demand_by_material[material.id] == 14.0
    finally:
        session.close()


def test_blocked_orders_unblock_after_purchase_order_delivery():
    session = make_session()
    try:
        sim_date = date(2026, 4, 19)
        seed_config(session, sim_date)
        material = create_material(session, "Stepper Motor")
        printer = create_printer(session)
        add_bom(session, printer, material, "5.0")
        order = create_order(session, printer, 2, OrderStatus.BLOCKED, reference_code="MO-001", sim_date=sim_date)

        supplier = Supplier(
            name="Motor Supplier",
            product_id=material.id,
            unit_cost=Decimal("12.5"),
            lead_time_days=0,
            quantity_breaks=None,
        )
        session.add(supplier)
        session.commit()
        session.refresh(supplier)

        po = PurchaseOrder(
            reference_code="PO-001",
            supplier_id=supplier.id,
            product_id=material.id,
            quantity=10,
            issue_date=sim_date,
            expected_delivery=sim_date,
            status=PurchaseOrderStatus.PENDING,
            unit_cost=Decimal("12.5"),
        )
        session.add(po)
        session.commit()

        results = PurchaseOrderService(session).process_deliveries(sim_date)
        session.refresh(order)

        assert results[0]["status"] == "delivered"
        assert order.status == OrderStatus.RELEASED
        assert order.status_reason is None
        assert session.query(Event).filter(Event.event_type == EventType.ORDER_UNBLOCKED_MATERIALS).count() == 1
    finally:
        session.close()


def test_manual_adjust_inventory_unblocks_blocked_orders():
    session = make_session()
    try:
        sim_date = date(2026, 4, 19)
        seed_config(session, sim_date)
        material = create_material(session, "Control Board")
        printer = create_printer(session)
        add_bom(session, printer, material, "5.0")
        order = create_order(session, printer, 1, OrderStatus.BLOCKED, reference_code="MO-001", sim_date=sim_date)

        manual_adjust_inventory(ManualAdjust(product_id=material.id, quantity=5), db=session)
        session.refresh(order)

        assert order.status == OrderStatus.RELEASED
        assert order.status_reason is None
    finally:
        session.close()


def test_blocked_orders_remain_blocked_when_inventory_is_still_insufficient():
    session = make_session()
    try:
        sim_date = date(2026, 4, 19)
        seed_config(session, sim_date)
        material = create_material(session, "LCD Screen")
        printer = create_printer(session)
        add_bom(session, printer, material, "4.0")
        order = create_order(session, printer, 2, OrderStatus.BLOCKED, reference_code="MO-001", sim_date=sim_date)

        InventoryService(session).update_inventory(material.id, Decimal("3"), "add")
        unblocked = OrderService(session).recheck_blocked_orders(sim_date)
        session.refresh(order)

        assert unblocked == []
        assert order.status == OrderStatus.BLOCKED
    finally:
        session.close()


def test_effective_daily_assembly_hours_use_lines_plus_workers_times_hours():
    session = make_session()
    try:
        config = seed_config(session)
        effective_hours = ConfigService(session).get_effective_daily_assembly_hours(config)
        assert effective_hours == 40.0
    finally:
        session.close()
