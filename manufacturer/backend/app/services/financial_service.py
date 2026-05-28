"""Financial management service for costs, revenues, and profit tracking."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import FinancialTransaction, FinancialTransactionType, SimulationConfig


class FinancialService:
    def __init__(self, db: Session):
        self.db = db

    def get_config(self) -> SimulationConfig:
        config = self.db.query(SimulationConfig).first()
        if not config:
            config = SimulationConfig()
            self.db.add(config)
            self.db.commit()
            self.db.refresh(config)
        return config

    def record_assembly_line_opened(self, sim_day: int) -> None:
        config = self.get_config()
        cost = Decimal(str(config.cost_per_assembly_line))
        transaction = FinancialTransaction(
            transaction_type=FinancialTransactionType.ASSEMBLY_LINE_OPENED,
            amount=-cost,
            description=f"Opened assembly line on day {sim_day}",
            sim_day=sim_day,
        )
        self.db.add(transaction)
        config.total_costs = float(config.total_costs) + float(cost)
        self.db.commit()

    def record_worker_hired(self, sim_day: int) -> None:
        config = self.get_config()
        cost = Decimal(str(config.cost_per_worker_per_hour * config.shift_hours))
        transaction = FinancialTransaction(
            transaction_type=FinancialTransactionType.WORKER_HIRED,
            amount=-cost,
            description=f"Hired worker on day {sim_day}",
            sim_day=sim_day,
        )
        self.db.add(transaction)
        config.total_costs = float(config.total_costs) + float(cost)
        self.db.commit()

    def record_worker_fired(self, sim_day: int) -> None:
        """Record cost (if any) of firing a worker. Currently zero, but reserved for severance/other costs."""
        transaction = FinancialTransaction(
            transaction_type=FinancialTransactionType.WORKER_FIRED,
            amount=Decimal("0"),
            description=f"Worker fired on day {sim_day}",
            sim_day=sim_day,
        )
        self.db.add(transaction)
        self.db.commit()

    def record_assembly_line_closed(self, sim_day: int) -> None:
        """Record closure of an assembly line. No refund of opening cost."""
        transaction = FinancialTransaction(
            transaction_type=FinancialTransactionType.ASSEMBLY_LINE_CLOSED,
            amount=Decimal("0"),
            description=f"Assembly line closed on day {sim_day}",
            sim_day=sim_day,
        )
        self.db.add(transaction)
        self.db.commit()

    def record_assembly_line_daily_costs(self, sim_day: int, num_lines: int) -> None:
        """Record daily maintenance/operating cost for all assembly lines."""
        config = self.get_config()
        cost = Decimal(str(config.cost_per_assembly_line_per_day * num_lines))
        transaction = FinancialTransaction(
            transaction_type=FinancialTransactionType.ASSEMBLY_LINE_DAILY_COST,
            amount=-cost,
            description=f"Daily cost for {num_lines} assembly lines on day {sim_day}",
            sim_day=sim_day,
        )
        self.db.add(transaction)
        config.total_costs = float(config.total_costs) + float(cost)
        self.db.commit()

    def record_worker_daily_costs(self, sim_day: int, num_workers: int) -> None:
        """Record daily wages for all workers."""
        config = self.get_config()
        cost = Decimal(str(config.cost_per_worker_per_hour * config.shift_hours * num_workers))
        transaction = FinancialTransaction(
            transaction_type=FinancialTransactionType.WORKER_DAILY_COST,
            amount=-cost,
            description=f"Daily wages for {num_workers} workers on day {sim_day}",
            sim_day=sim_day,
        )
        self.db.add(transaction)
        config.total_costs = float(config.total_costs) + float(cost)
        self.db.commit()

    def record_materials_purchased(self, sim_day: int, cost: float, description: str) -> None:
        config = self.get_config()
        transaction = FinancialTransaction(
            transaction_type=FinancialTransactionType.MATERIALS_PURCHASED,
            amount=-Decimal(str(cost)),
            description=description,
            sim_day=sim_day,
        )
        self.db.add(transaction)
        config.total_costs = float(config.total_costs) + cost
        self.db.commit()

    def record_product_sold(self, sim_day: int, revenue: float, product_name: str, quantity: int) -> None:
        config = self.get_config()
        transaction = FinancialTransaction(
            transaction_type=FinancialTransactionType.PRODUCT_SOLD,
            amount=Decimal(str(revenue)),
            description=f"Sold {quantity} {product_name}",
            sim_day=sim_day,
        )
        self.db.add(transaction)
        config.total_revenue = float(config.total_revenue) + revenue
        self.db.commit()

    def get_financial_summary(self) -> dict[str, Any]:
        config = self.get_config()
        return {
            "total_costs": float(config.total_costs),
            "total_revenue": float(config.total_revenue),
            "net_profit": float(config.total_revenue) - float(config.total_costs),
            "cost_per_assembly_line": float(config.cost_per_assembly_line),
            "cost_per_assembly_line_per_day": float(config.cost_per_assembly_line_per_day),
            "cost_per_worker_per_hour": float(config.cost_per_worker_per_hour),
            "max_workers_per_line": config.max_workers_per_line,
        }

    def get_transactions(self, sim_day: int | None = None) -> list[dict[str, Any]]:
        """Get financial transactions, optionally filtered by engine day.

        When sim_day is provided, it's interpreted as an engine day number.
        After day advance, sim_day is incremented, and transactions are recorded with the new sim_day.
        So engine day N gets transactions recorded with sim_day = N (after that day's advance).
        """
        query = self.db.query(FinancialTransaction)
        if sim_day is not None:
            query = query.filter(FinancialTransaction.sim_day == sim_day)
        transactions = query.order_by(FinancialTransaction.created_at).all()
        return [
            {
                "type": t.transaction_type.value,
                "amount": float(t.amount),
                "description": t.description,
                "sim_day": t.sim_day,
            }
            for t in transactions
        ]
