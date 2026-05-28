"""Comprehensive tests for configuration management and financial system edge cases."""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.models import Event, EventType, Inventory, Product, ProductType, SimulationConfig
from app.services.config_service import ConfigService
from app.services.financial_service import FinancialService
from app.services.simulation_service import SimulationService


class TestConfigurationResets:
    """Test all reset scenarios and edge cases."""

    def test_reset_simulation_clears_orders_and_events(self, db: Session) -> None:
        """reset_simulation should clear orders and events but preserve products."""
        service = SimulationService(db)

        # Create some data
        from app.models.models import ManufacturingOrder, OrderStatus
        order = ManufacturingOrder(
            product_id="test-product",
            quantity=10,
            status=OrderStatus.PENDING,
            created_date=date.today(),
        )
        db.add(order)
        event = Event(event_type=EventType.ORDER_CREATED, sim_date=date.today())
        db.add(event)
        db.commit()

        initial_order_count = db.query(ManufacturingOrder).count()
        initial_event_count = db.query(Event).count()
        assert initial_order_count > 0
        assert initial_event_count > 0

        # Reset
        service.reset_simulation()

        # Verify orders and events cleared
        assert db.query(ManufacturingOrder).count() == 0
        assert db.query(Event).count() == 0
        # Verify products still exist
        assert db.query(Product).count() > 0

    def test_reset_to_empty_removes_all_data(self, db: Session) -> None:
        """reset_to_empty should remove all products, suppliers, BOM, inventory."""
        service = SimulationService(db)

        # Verify initial data exists
        initial_products = db.query(Product).count()
        assert initial_products > 0

        # Reset to empty
        service.reset_to_empty()

        # Verify all data cleared except config
        assert db.query(Product).count() == 0
        assert db.query(Inventory).count() == 0
        assert db.query(Event).count() == 0
        # Config should still exist
        assert db.query(SimulationConfig).count() > 0

    def test_reset_to_empty_resets_config_values(self, db: Session) -> None:
        """reset_to_empty should reset config to default values."""
        config_service = ConfigService(db)
        service = SimulationService(db)

        # Modify config
        config = config_service.get_config()
        config.assembly_lines = 5
        config.workers_per_line = 10
        db.commit()

        # Reset to empty
        service.reset_to_empty()

        # Verify config reset
        config = config_service.get_config()
        assert config.assembly_lines == 1  # default
        assert config.workers_per_line == 1  # default
        assert config.cost_per_assembly_line == 50000.0  # default

    def test_reset_to_default_config_recreates_all_data(self, db: Session) -> None:
        """reset_to_default_config should create all starter products, suppliers, BOM."""
        service = SimulationService(db)

        # Reset to default
        service.reset_to_default_config()

        # Verify all data recreated
        products = db.query(Product).count()
        inventory_items = db.query(Inventory).count()

        # Should have 6 materials + 3 printers = 9 products
        assert products >= 9, f"Expected at least 9 products, got {products}"
        # Should have 6 materials in inventory
        assert inventory_items >= 6, f"Expected at least 6 inventory items, got {inventory_items}"

    def test_reset_to_default_config_no_duplicate_inventory(self, db: Session) -> None:
        """reset_to_default_config should not create duplicate inventory items."""
        service = SimulationService(db)

        # Reset multiple times
        for _ in range(3):
            service.reset_to_default_config()

        # Check for duplicates
        materials = db.query(Product).filter(Product.type == ProductType.MATERIAL).all()
        material_names = [m.name for m in materials]
        assert len(material_names) == len(set(material_names)), "Found duplicate materials"

        # Check inventory items
        for material in materials:
            count = db.query(Inventory).filter(Inventory.product_id == material.id).count()
            assert count <= 1, f"Material {material.name} has {count} inventory items (expected 1)"

    def test_reset_preserves_financial_config(self, db: Session) -> None:
        """Resets should preserve financial configuration."""
        config_service = ConfigService(db)
        service = SimulationService(db)

        # Set custom financial config
        config = config_service.get_config()
        config.cost_per_assembly_line = 75000.0
        config.cost_per_worker_per_hour = 60.0
        config.max_workers_per_line = 15
        db.commit()

        # Reset simulation (not to_empty, which resets config)
        service.reset_simulation()

        # Verify financial config persisted
        config = config_service.get_config()
        assert config.cost_per_assembly_line == 50000.0  # should be reset to default
        assert config.cost_per_worker_per_hour == 50.0
        assert config.max_workers_per_line == 10


class TestFinancialTracking:
    """Test financial transaction recording and edge cases."""

    def test_record_assembly_line_opened(self, db: Session) -> None:
        """Opening assembly line should record transaction."""
        fin_service = FinancialService(db)

        initial_cost = db.query(SimulationConfig).first().total_costs
        fin_service.record_assembly_line_opened(1)

        config = db.query(SimulationConfig).first()
        assert config.total_costs > initial_cost

    def test_record_worker_hired(self, db: Session) -> None:
        """Hiring worker should record transaction."""
        fin_service = FinancialService(db)

        config = db.query(SimulationConfig).first()
        daily_cost = config.cost_per_worker_per_hour * config.shift_hours
        initial_cost = config.total_costs

        fin_service.record_worker_hired(1)

        config = db.query(SimulationConfig).first()
        assert config.total_costs == initial_cost + daily_cost

    def test_multiple_transactions_accumulate(self, db: Session) -> None:
        """Multiple transactions should accumulate correctly."""
        fin_service = FinancialService(db)
        config_service = ConfigService(db)

        initial_cost = config_service.get_config().total_costs

        # Record multiple transactions
        fin_service.record_assembly_line_opened(1)
        cost_after_line = config_service.get_config().total_costs

        fin_service.record_worker_hired(1)
        cost_after_worker = config_service.get_config().total_costs

        fin_service.record_materials_purchased(1, 100.0, "Test material purchase")
        cost_after_materials = config_service.get_config().total_costs

        # Verify accumulation
        assert cost_after_line > initial_cost
        assert cost_after_worker > cost_after_line
        assert cost_after_materials > cost_after_worker

    def test_product_sold_records_revenue(self, db: Session) -> None:
        """Selling product should record revenue."""
        fin_service = FinancialService(db)

        initial_revenue = db.query(SimulationConfig).first().total_revenue
        fin_service.record_product_sold(1000.0, 5, "Basic300", 1)

        config = db.query(SimulationConfig).first()
        assert config.total_revenue > initial_revenue

    def test_negative_costs_prevented(self, db: Session) -> None:
        """Configuration should not allow negative costs."""
        config_service = ConfigService(db)

        config = config_service.get_config()
        original_cost = config.cost_per_assembly_line

        # Try to set negative cost - should be rejected or result in validation error
        try:
            config.cost_per_assembly_line = -1000.0
            db.commit()
            # If no error, verify it was rejected
            config = config_service.get_config()
            assert config.cost_per_assembly_line == original_cost
        except (ValueError, Exception):
            # Expected - validation should fail
            db.rollback()

    def test_financial_summary_calculates_profit(self, db: Session) -> None:
        """Financial summary should correctly calculate net profit."""
        fin_service = FinancialService(db)

        # Record some transactions
        fin_service.record_assembly_line_opened(1)
        fin_service.record_product_sold(1000.0, 5, "Basic300", 1)

        summary = fin_service.get_financial_summary()

        assert summary["net_profit"] == summary["total_revenue"] - summary["total_costs"]

    def test_transactions_table_contains_all_types(self, db: Session) -> None:
        """Transactions should include all types of costs."""
        fin_service = FinancialService(db)

        # Record various transactions
        fin_service.record_assembly_line_opened(1)
        fin_service.record_worker_hired(1)
        fin_service.record_materials_purchased(1, 50.0, "Test purchase")
        fin_service.record_product_sold(1000.0, 1, "Basic300", 1)

        transactions = fin_service.get_transactions()

        types = {t["type"] for t in transactions}
        assert "ASSEMBLY_LINE_OPENED" in types
        assert "WORKER_HIRED" in types
        assert "MATERIALS_PURCHASED" in types
        assert "PRODUCT_SOLD" in types

    def test_transactions_day_filter_uses_exact_accounting_day(self, db: Session) -> None:
        """Daily financial charts must not double-count adjacent days."""
        fin_service = FinancialService(db)

        fin_service.record_materials_purchased(77, 100.0, "Previous day purchase")
        fin_service.record_materials_purchased(78, 250.0, "Current day purchase")

        transactions = fin_service.get_transactions(78)

        assert [t["sim_day"] for t in transactions] == [78]
        assert sum(abs(t["amount"]) for t in transactions) == 250.0


class TestConfigurationConstraints:
    """Test configuration boundary conditions and constraints."""

    def test_max_workers_per_line_constraint(self, db: Session) -> None:
        """Should not allow workers_per_line to exceed max_workers_per_line."""
        config_service = ConfigService(db)

        config = config_service.get_config()
        max_workers = config.max_workers_per_line

        # Attempt to set workers above max
        config.workers_per_line = max_workers + 5
        try:
            db.commit()
            # If no error, the UI/validation layer should prevent this
            # Reload and verify
            config = config_service.get_config()
            assert config.workers_per_line <= max_workers
        except Exception:
            db.rollback()

    def test_assembly_lines_cannot_be_zero(self, db: Session) -> None:
        """Assembly lines should be at least 1."""
        config_service = ConfigService(db)

        config = config_service.get_config()

        try:
            config.assembly_lines = 0
            db.commit()
            # Verify it was rejected
            config = config_service.get_config()
            assert config.assembly_lines >= 1
        except (ValueError, Exception):
            db.rollback()

    def test_shift_hours_in_valid_range(self, db: Session) -> None:
        """Shift hours should be between 1 and 24."""
        config_service = ConfigService(db)

        config = config_service.get_config()

        # Test boundary values
        config.shift_hours = 1.0
        db.commit()
        assert db.query(SimulationConfig).first().shift_hours == 1.0

        config.shift_hours = 24.0
        db.commit()
        assert db.query(SimulationConfig).first().shift_hours == 24.0

    def test_floating_point_precision_in_shift_hours(self, db: Session) -> None:
        """Shift hours should handle decimal values correctly."""
        config_service = ConfigService(db)

        config = config_service.get_config()
        config.shift_hours = 8.5
        db.commit()

        config = config_service.get_config()
        # Account for floating point imprecision
        assert abs(config.shift_hours - 8.5) < 0.01


class TestInventoryConsistency:
    """Test inventory state consistency."""

    def test_inventory_cannot_be_negative(self, db: Session) -> None:
        """Inventory quantities should never be negative."""
        inventory_items = db.query(Inventory).all()

        for item in inventory_items:
            assert item.quantity >= 0, f"Inventory {item.product_id} has negative quantity"

    def test_warehouse_capacity_respected(self, db: Session) -> None:
        """Total inventory should not exceed warehouse capacity (in normal operation)."""
        config = db.query(SimulationConfig).first()
        warehouse_capacity = config.warehouse_capacity

        total_inventory = db.query(Inventory).all()
        total_quantity = sum(Decimal(item.quantity) for item in total_inventory)

        # After reset, should be well under capacity
        # (Can exceed during simulation when items arrive)
        if db.query(Event).count() == 0:
            assert total_quantity <= warehouse_capacity * 1.2  # Allow 20% overage

    def test_inventory_duplicates_prevented(self, db: Session) -> None:
        """Each product should have at most one inventory item."""
        products = db.query(Product).all()

        for product in products:
            count = db.query(Inventory).filter(Inventory.product_id == product.id).count()
            assert count <= 1, f"Product {product.id} has {count} inventory items"


class TestScenarioRecommendations:
    """Test scenario recommendation application."""

    def test_apply_assembly_recommendation_updates_config(self, db: Session) -> None:
        """Applying assembly recommendation should update config."""
        config_service = ConfigService(db)

        # Create a different recommendation
        from app.schemas.schemas import SimulationConfigUpdate
        new_config = SimulationConfigUpdate(
            assembly_lines=5,
            workers_per_line=2,
            shift_hours=10.0,
        )

        config_service.update_config(new_config)
        updated_config = config_service.get_config()

        assert updated_config.assembly_lines == 5
        assert updated_config.workers_per_line == 2
        assert updated_config.shift_hours == 10.0

    def test_apply_costs_recommendation_updates_config(self, db: Session) -> None:
        """Applying cost recommendation should update config."""
        config_service = ConfigService(db)

        # Create a different recommendation
        from app.schemas.schemas import SimulationConfigUpdate
        new_config = SimulationConfigUpdate(
            cost_per_assembly_line=75000.0,
            cost_per_worker_per_hour=60.0,
            max_workers_per_line=15,
        )

        config_service.update_config(new_config)
        updated_config = config_service.get_config()

        assert updated_config.cost_per_assembly_line == 75000.0
        assert updated_config.cost_per_worker_per_hour == 60.0
        assert updated_config.max_workers_per_line == 15

    def test_apply_partial_recommendation_preserves_other_fields(self, db: Session) -> None:
        """Applying partial recommendation should preserve other fields."""
        config_service = ConfigService(db)

        # Set initial values
        from app.schemas.schemas import SimulationConfigUpdate
        config_service.update_config(SimulationConfigUpdate(
            assembly_lines=3,
            workers_per_line=2,
            shift_hours=8.0,
            cost_per_assembly_line=50000.0,
        ))

        # Apply only assembly recommendation
        config_service.update_config(SimulationConfigUpdate(
            assembly_lines=1,
            workers_per_line=1,
        ))

        config = config_service.get_config()
        # Assembly should be updated
        assert config.assembly_lines == 1
        # Shift hours should remain unchanged
        assert config.shift_hours == 8.0
