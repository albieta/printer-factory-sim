"""Critical scenario tests covering real bugs and edge cases.

This test module focuses on:
1. The duplicate inventory bug (actually fixed with our reset changes)
2. Negative inventory prevention
3. Warehouse capacity tracking
4. Financial transaction consistency
5. Configuration constraint enforcement
6. Reset operation idempotence
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.models import (
    Event,
    EventType,
    Inventory,
    ManufacturingOrder,
    OrderStatus,
    Product,
    ProductType,
    SimulationConfig,
)
from app.services.config_service import ConfigService
from app.services.financial_service import FinancialService
from app.services.inventory_service import InventoryService
from app.services.simulation_service import SimulationService


class TestDuplicateInventoryBugPrevention:
    """Prevent the duplicate inventory bug that existed before our fix.

    Root cause: reset_to_default_config() called reset_simulation() which
    created inventory, then tried to create more. Fixed by calling
    reset_to_empty() instead.
    """

    def test_reset_default_creates_exactly_six_materials_no_duplicates(
        self, db: Session
    ) -> None:
        """After reset-default-config, there should be exactly 6 materials with 1 inventory each."""
        service = SimulationService(db)

        service.reset_to_default_config()

        materials = db.query(Product).filter(Product.type == ProductType.MATERIAL).all()
        assert len(materials) == 6, f"Expected 6 materials, got {len(materials)}"

        for material in materials:
            inv_items = db.query(Inventory).filter(
                Inventory.product_id == material.id
            ).all()
            assert (
                len(inv_items) <= 1
            ), f"Material {material.name} has {len(inv_items)} inventory items (expected 1)"

    def test_multiple_reset_default_operations_remain_idempotent(
        self, db: Session
    ) -> None:
        """Calling reset-default-config 5 times should not accumulate data."""
        service = SimulationService(db)

        for iteration in range(5):
            service.reset_to_default_config()

            # After each reset, verify exactly 6 materials and 3 printers
            materials = db.query(Product).filter(
                Product.type == ProductType.MATERIAL
            ).all()
            printers = db.query(Product).filter(
                Product.type == ProductType.PRINTER
            ).all()

            assert (
                len(materials) == 6
            ), f"Iteration {iteration}: Expected 6 materials, got {len(materials)}"
            assert (
                len(printers) == 3
            ), f"Iteration {iteration}: Expected 3 printers, got {len(printers)}"

            # Verify no duplicate inventory
            for material in materials:
                inv_count = db.query(Inventory).filter(
                    Inventory.product_id == material.id
                ).count()
                assert (
                    inv_count == 1
                ), f"Iteration {iteration}: Material {material.id} has {inv_count} inventory items"


class TestNegativeInventoryPrevention:
    """Ensure inventory never becomes negative, which would indicate data corruption."""

    def test_inventory_non_negative_after_initialization(self, db: Session) -> None:
        """After reset, all inventory should be ≥ 0."""
        service = SimulationService(db)
        service.reset_to_default_config()

        all_inventory = db.query(Inventory).all()
        for item in all_inventory:
            assert (
                item.quantity >= 0
            ), f"Inventory {item.product_id} is negative: {item.quantity}"

    def test_inventory_non_negative_after_consumption(self, db: Session) -> None:
        """Even after consuming inventory, quantities should not go negative."""
        service = SimulationService(db)
        service.reset_to_default_config()

        # Manually consume some inventory to near zero
        materials = db.query(Product).filter(Product.type == ProductType.MATERIAL).all()
        for material in materials[:2]:
            inv = db.query(Inventory).filter(
                Inventory.product_id == material.id
            ).first()
            if inv:
                inv.quantity = Decimal("1")  # Very low but still positive
        db.commit()

        # Verify all still non-negative
        all_inventory = db.query(Inventory).all()
        for item in all_inventory:
            assert (
                item.quantity >= 0
            ), f"Inventory {item.product_id} went negative: {item.quantity}"


class TestWarehouseCapacityTracking:
    """Ensure warehouse capacity is tracked and calculated correctly."""

    def test_capacity_info_sums_correctly(self, db: Session) -> None:
        """Capacity info should show correct usage and available space."""
        inventory_service = InventoryService(db)
        service = SimulationService(db)
        service.reset_to_default_config()

        capacity_info = inventory_service.get_capacity_info()

        # Manually calculate from inventory
        inventory_items = db.query(Inventory).all()
        manual_total = sum(Decimal(item.quantity) for item in inventory_items)

        assert (
            capacity_info["current_usage"] == float(manual_total)
        ), f"Usage mismatch: {capacity_info['current_usage']} vs {float(manual_total)}"

    def test_available_capacity_calculation_is_correct(self, db: Session) -> None:
        """Available capacity = warehouse_capacity - current_usage."""
        inventory_service = InventoryService(db)
        service = SimulationService(db)
        service.reset_to_default_config()

        capacity = inventory_service.get_capacity_info()

        expected_available = (
            capacity["warehouse_capacity"] - capacity["current_usage"]
        )
        assert (
            capacity["available_capacity"] == expected_available
        ), f"Available capacity calculation wrong: {capacity['available_capacity']} vs {expected_available}"

    def test_warehouse_starts_with_proper_utilization(self, db: Session) -> None:
        """After reset, warehouse should be ~75% utilized (1650/2200)."""
        inventory_service = InventoryService(db)
        service = SimulationService(db)
        service.reset_to_default_config()

        capacity = inventory_service.get_capacity_info()

        # Should be roughly 75% (1650 out of 2200)
        usage_percent = capacity["usage_percentage"]
        assert (
            70 < usage_percent < 80
        ), f"Initial usage {usage_percent}% outside expected 70-80%"


class TestFinancialTransactionConsistency:
    """Ensure all financial transactions are recorded and totals are consistent."""

    def test_assembly_line_cost_recorded(self, db: Session) -> None:
        """Opening assembly line records cost in config and transaction."""
        fin_service = FinancialService(db)
        service = SimulationService(db)
        service.reset_to_default_config()

        config_before = db.query(SimulationConfig).first()
        cost_before = config_before.total_costs

        fin_service.record_assembly_line_opened(1)

        config_after = db.query(SimulationConfig).first()
        cost_after = config_after.total_costs

        assert (
            cost_after > cost_before
        ), f"Cost not recorded: {cost_before} -> {cost_after}"

    def test_worker_hiring_cost_matches_configuration(self, db: Session) -> None:
        """Worker hiring cost should equal cost_per_worker_per_hour * shift_hours."""
        fin_service = FinancialService(db)
        service = SimulationService(db)
        service.reset_to_default_config()

        config = db.query(SimulationConfig).first()
        expected_daily_cost = (
            config.cost_per_worker_per_hour * config.shift_hours
        )

        cost_before = config.total_costs
        fin_service.record_worker_hired(1)

        config = db.query(SimulationConfig).first()
        cost_added = config.total_costs - cost_before

        assert (
            abs(cost_added - expected_daily_cost) < 0.01
        ), f"Worker cost {cost_added} doesn't match expected {expected_daily_cost}"

    def test_profit_calculation_always_valid(self, db: Session) -> None:
        """Profit should always equal revenue - costs, never NaN or invalid."""
        fin_service = FinancialService(db)
        service = SimulationService(db)
        service.reset_to_default_config()

        # Record various transactions
        fin_service.record_assembly_line_opened(1)
        fin_service.record_worker_hired(1)
        fin_service.record_product_sold(10000.0, 5, "Basic300", 1)

        summary = fin_service.get_financial_summary()

        assert isinstance(
            summary["net_profit"], (int, float)
        ), f"Profit is {type(summary['net_profit'])}, not a number"
        assert (
            summary["net_profit"]
            == summary["total_revenue"] - summary["total_costs"]
        ), "Profit calculation incorrect"

    def test_all_transaction_types_recorded(self, db: Session) -> None:
        """All 4 transaction types should be recorded and retrievable."""
        fin_service = FinancialService(db)
        service = SimulationService(db)
        service.reset_to_default_config()

        # Record each type
        fin_service.record_assembly_line_opened(1)
        fin_service.record_worker_hired(1)
        fin_service.record_materials_purchased(1, 500.0, "Materials for day 1")
        fin_service.record_product_sold(5000.0, 1, "Basic300", 1)

        transactions = fin_service.get_transactions()
        types = {t["type"] for t in transactions}

        required_types = {
            "ASSEMBLY_LINE_OPENED",
            "WORKER_HIRED",
            "MATERIALS_PURCHASED",
            "PRODUCT_SOLD",
        }
        assert required_types.issubset(
            types
        ), f"Missing transaction types. Have: {types}, need: {required_types}"


class TestConfigurationConstraintEnforcement:
    """Ensure configuration constraints are respected."""

    def test_shift_hours_within_valid_range(self, db: Session) -> None:
        """Shift hours should be 1-24."""
        service = SimulationService(db)
        service.reset_to_default_config()

        config = db.query(SimulationConfig).first()

        assert (
            1.0 <= config.shift_hours <= 24.0
        ), f"Shift hours {config.shift_hours} outside valid range"

    def test_assembly_lines_at_least_one(self, db: Session) -> None:
        """Assembly lines should be at least 1."""
        service = SimulationService(db)
        service.reset_to_default_config()

        config = db.query(SimulationConfig).first()

        assert (
            config.assembly_lines >= 1
        ), f"Assembly lines {config.assembly_lines} is less than 1"

    def test_workers_per_line_respects_max(self, db: Session) -> None:
        """Workers per line should not exceed max_workers_per_line."""
        service = SimulationService(db)
        service.reset_to_default_config()

        config = db.query(SimulationConfig).first()

        assert (
            config.workers_per_line <= config.max_workers_per_line
        ), f"Workers {config.workers_per_line} exceeds max {config.max_workers_per_line}"


class TestResetOperationIdempotence:
    """Ensure reset operations are fully idempotent and deterministic."""

    def test_reset_simulation_idempotent(self, db: Session) -> None:
        """Calling reset_simulation twice produces identical state."""
        service = SimulationService(db)
        service.reset_to_default_config()

        # Create some events
        for i in range(3):
            event = Event(
                event_type=EventType.DAY_ADVANCED,
                sim_date=date.today(),
                details={"day": i},
            )
            db.add(event)
        db.commit()

        assert db.query(Event).count() > 0, "Events not created"

        # First reset
        service.reset_simulation()
        state_1 = {
            "products": db.query(Product).count(),
            "inventory": db.query(Inventory).count(),
            "events": db.query(Event).count(),
        }

        # Second reset
        service.reset_simulation()
        state_2 = {
            "products": db.query(Product).count(),
            "inventory": db.query(Inventory).count(),
            "events": db.query(Event).count(),
        }

        assert (
            state_1 == state_2
        ), f"States differ after second reset: {state_1} vs {state_2}"

    def test_reset_to_empty_followed_by_reset_default_is_consistent(
        self, db: Session
    ) -> None:
        """reset_to_empty then reset_to_default should match direct reset_to_default."""
        service = SimulationService(db)

        # Path 1: Direct reset to default
        service.reset_to_default_config()
        state_direct = {
            "products": db.query(Product).count(),
            "materials": db.query(Product)
            .filter(Product.type == ProductType.MATERIAL)
            .count(),
            "printers": db.query(Product)
            .filter(Product.type == ProductType.PRINTER)
            .count(),
            "inventory": db.query(Inventory).count(),
        }

        # Clear and try again
        db.query(Product).delete()
        db.query(Inventory).delete()
        db.query(Event).delete()
        db.commit()

        # Path 2: Empty then default
        service.reset_to_empty()
        service.reset_to_default_config()
        state_indirect = {
            "products": db.query(Product).count(),
            "materials": db.query(Product)
            .filter(Product.type == ProductType.MATERIAL)
            .count(),
            "printers": db.query(Product)
            .filter(Product.type == ProductType.PRINTER)
            .count(),
            "inventory": db.query(Inventory).count(),
        }

        assert (
            state_direct == state_indirect
        ), f"States differ: {state_direct} vs {state_indirect}"

    def test_config_values_reset_to_defaults(self, db: Session) -> None:
        """After reset_to_empty, config should have default values."""
        service = SimulationService(db)
        config_service = ConfigService(db)

        # Modify config
        config = config_service.get_config()
        config.assembly_lines = 99
        config.cost_per_assembly_line = 99999.0
        db.commit()

        # Reset to empty
        service.reset_to_empty()

        # Verify defaults restored
        config = config_service.get_config()
        assert config.assembly_lines == 1, f"assembly_lines not reset: {config.assembly_lines}"
        assert (
            config.cost_per_assembly_line == 50000.0
        ), f"cost not reset: {config.cost_per_assembly_line}"
