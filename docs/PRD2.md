# Product Requirements Document v2
# 3D Printer Production Simulator

## Purpose of This Document

This document is a second PRD created after implementation work had already progressed. It is meant to be compared against the original `PRD.md` so that the evolution of the project is visible. The original PRD is preserved unchanged as the initial planning artifact. This document reflects the actual repository state more closely, including the architectural changes made during development.

## Version

- Date: 2026-04-24
- Status: Retrospective PRD aligned with the current repository

## 1. Project Summary

The 3D Printer Production Simulator is a full-stack web application that simulates the daily operation of a factory producing 3D printers. The user acts as a production planner and interacts with the system through a web interface. The simulator models incoming manufacturing demand, bill of materials requirements, inventory levels, warehouse capacity, supplier lead times, purchase orders, production capacity, and event history.

The project began from the course brief and an original PRD-first workflow. During implementation, the team changed part of the technical direction. The current repository uses a FastAPI backend with SQLite persistence and a React + Vite frontend. The team also chose to build a custom day-advance simulation flow instead of using SimPy.

## 2. What the System Does

### 2.1 Implemented functionality

- generates manufacturing orders at the start of each simulated day
- stores printer models, raw materials, suppliers, BOMs, inventory, purchase orders, manufacturing orders, events, and simulation configuration
- lets the planner review demand and release or reject manufacturing orders
- checks BOM requirements against inventory before or during production
- tracks blocked orders when materials are missing
- allows supplier creation and purchase-order creation with lead times and quantity breaks
- processes purchase-order arrivals on the correct simulated date
- rejects inbound purchase orders when warehouse capacity would be exceeded
- executes production using a shared daily assembly-capacity model
- logs events for demand, production, procurement, and day advancement
- exports JSON snapshots for full state, inventory-only, and events-only views
- restores previously exported full-state snapshots through JSON import
- exposes the simulator through REST endpoints with Swagger/OpenAPI documentation

### 2.2 Implemented but incomplete

- a Streamlit dashboard file exists in the repository, but it is not the active user interface

### 2.3 Verified repository state

Local verification in the repository showed:

- frontend build passes with `npm run build`
- backend operations tests pass with `../.venv/bin/pytest tests/test_operations_flow.py`

## 3. Key Decisions and Changes from the Original Direction

### 3.1 Frontend stack change

The original course suggestion used Streamlit for the UI. During implementation, the generated Streamlit-based direction was causing problems for the team. Codex proposed trying a React + Vite frontend instead. After evaluating the results, the team decided to adopt that alternative stack early while the cost of switching was still low.

This means the repository now contains:

- an active React frontend in `frontend/`
- a legacy Streamlit prototype in `backend/app/ui/dashboard.py`

The React approach was ultimately preferred because the quality of the generated interface and the overall results were better.

### 3.2 Simulation engine choice

The course brief recommended SimPy, but the team deliberately chose not to use it. Instead, the project implements its own simulation flow in backend services. This was partly a technical choice and partly an experiment in AI-assisted software generation: the team wanted to see how far the agent could go in helping build the simulation rules directly without relying on SimPy.

### 3.3 Tooling change from Claude Code to Codex

The project initially started with Claude Code using the teacher-provided API setup. After the class session, that access path was no longer available. The team then tried using Qwen directly with a personal free-tier setup, but the available usage was exhausted almost immediately. At that point the team needed a practical replacement and switched to Codex, partly because one team member had a subscription and Codex was also available through ChatGPT's free tier.

The team observed better results after switching to Codex, and from that point onward the implementation advanced more successfully.

## 4. Architecture

## 4.1 High-level view

```text
React + Vite frontend
        |
        | HTTP / JSON
        v
FastAPI route layer
        |
        v
Service layer
  - ConfigService
  - OrderService
  - InventoryService
  - SupplierService / PurchaseOrderService
  - ProductionService
  - SimulationService
  - EventService
        |
        v
SQLite database via SQLAlchemy
```

## 4.2 Backend

The backend is implemented in `backend/` and uses:

- FastAPI for HTTP routes and OpenAPI generation
- SQLAlchemy for persistence
- Pydantic for API schemas
- SQLite as the local database

Backend responsibilities include:

- storing and retrieving simulation state
- validating and updating configuration
- generating daily demand
- releasing, rejecting, blocking, and completing manufacturing orders
- creating and receiving purchase orders
- checking warehouse capacity
- logging events
- exporting JSON snapshots

## 4.3 Frontend

The active frontend is implemented in `frontend/` and uses:

- React 18
- TypeScript
- Vite
- React Router
- Bootstrap / React Bootstrap
- Plotly
- Axios

The main pages are:

- `/` overview
- `/orders`
- `/inventory`
- `/suppliers`
- `/production`
- `/reports`
- `/settings`

The Settings page now includes the scenario-restore control used to import a previously exported full-state JSON snapshot back into the simulator.

## 4.4 Daily simulation flow

The current day-advance flow works as follows:

1. increment the simulation date
2. process due purchase-order deliveries
3. generate random new manufacturing orders
4. recheck blocked orders
5. execute production for released orders under the current capacity limit
6. log a `DAY_ADVANCED` summary event

This logic is centered in `SimulationService.advance_day()`.

## 5. Data Model

The current implementation follows the course brief closely, with a few additions for traceability and status explanation.

### 5.1 Product

Represents both printer models and raw materials.

Fields:

- `id`
- `name`
- `type`
- `assembly_hours`
- `created_at`

### 5.2 BillOfMaterials

Defines the quantity of each raw material needed to produce one unit of a printer model.

Fields:

- `id`
- `finished_product_id`
- `material_id`
- `quantity`

### 5.3 Supplier

Represents a supplier for a material, including lead time and pricing rules.

Fields:

- `id`
- `name`
- `product_id`
- `unit_cost`
- `lead_time_days`
- `quantity_breaks`

### 5.4 Inventory

Stores on-hand stock for raw materials.

Fields:

- `product_id`
- `quantity`
- `last_updated`

### 5.5 ManufacturingOrder

Represents customer demand for finished printers.

Fields:

- `id`
- `reference_code`
- `product_id`
- `quantity`
- `status`
- `status_reason`
- `created_date`
- `released_date`
- `completed_date`

Statuses:

- `PENDING`
- `RELEASED`
- `COMPLETED`
- `BLOCKED`
- `REJECTED`

### 5.6 PurchaseOrder

Represents procurement of raw materials.

Fields:

- `id`
- `reference_code`
- `supplier_id`
- `product_id`
- `quantity`
- `issue_date`
- `expected_delivery`
- `actual_delivery`
- `status`
- `status_reason`
- `unit_cost`

Statuses:

- `PENDING`
- `DELIVERED`
- `REJECTED`

### 5.7 Event

Stores the historical trace of what happened in the simulator.

Fields:

- `id`
- `event_type`
- `sim_date`
- `timestamp`
- `details`

Implemented event types include:

- `ORDER_CREATED`
- `ORDER_RELEASED`
- `ORDER_BLOCKED_MATERIALS`
- `ORDER_UNBLOCKED_MATERIALS`
- `ORDER_REJECTED`
- `ORDER_COMPLETED`
- `PO_CREATED`
- `PO_DELIVERED`
- `PO_REJECTED_CAPACITY`
- `MATERIAL_CONSUMED`
- `INVENTORY_ADDED`
- `DAY_ADVANCED`
- `PRODUCTION_BLOCKED_CAPACITY`

### 5.8 SimulationConfig

Stores the global parameters for the simulator.

Fields:

- `warehouse_capacity`
- `daily_assembly_hours`
- `assembly_lines`
- `workers_per_line`
- `shift_hours`
- `demand_distribution_mean`
- `demand_distribution_variance`
- `sim_date`

## 6. Capacity Model

The current implementation uses a simple shared-capacity formula:

```text
effective_daily_assembly_hours =
assembly_lines * workers_per_line * shift_hours
```

This replaces a simpler single-value interpretation of assembly capacity with a model that is still easy to reason about in the UI.

## 7. REST API

The project exposes its functionality under `/api`.

### 7.1 Configuration

- `GET /api/config/`
- `PUT /api/config/`
- `GET /api/config/printer-models`
- `POST /api/config/printer-models`
- `DELETE /api/config/printer-models/{printer_id}`

### 7.2 Materials and BOM

- `GET /api/materials/`
- `POST /api/materials/`
- `GET /api/materials/bom`
- `POST /api/materials/bom`
- `DELETE /api/materials/bom/{bom_id}`

### 7.3 Suppliers and purchase orders

- `GET /api/suppliers/`
- `POST /api/suppliers/`
- `PUT /api/suppliers/{supplier_id}`
- `DELETE /api/suppliers/{supplier_id}`
- `GET /api/orders/purchase/`
- `POST /api/orders/purchase/`

### 7.4 Inventory

- `GET /api/inventory/`
- `GET /api/inventory/capacity`
- `POST /api/inventory/manual-adjust`

### 7.5 Manufacturing orders

- `GET /api/orders/mfg`
- `POST /api/orders/mfg/release`
- `POST /api/orders/mfg/reject`
- `GET /api/orders/mfg/{order_id}`
- `GET /api/orders/mfg/{order_id}/requirements`

### 7.6 Simulation and events

- `GET /api/simulation/status`
- `POST /api/simulation/advance-day`
- `POST /api/simulation/reset`
- `GET /api/events/`
- `GET /api/events/timeseries/{metric}`

### 7.7 Import/export

- `GET /api/export/full-state/`
- `GET /api/export/inventory-only/`
- `GET /api/export/events-only/`
- `POST /api/import/full-state/`

### 7.8 Metadata

- `GET /health`
- `GET /docs`
- `GET /redoc`
- `GET /openapi.json`

## 8. Seeded Starter Scenario

The repository seeds the simulator with:

- 3 printer models
- 6 raw materials
- 6 suppliers
- starter inventory
- default simulation configuration

This seeded profile is also used by the reset functionality.

## 9. Current Milestone Status

### 9.1 Completed in the repository

- working backend and frontend scaffold
- data model and SQLite persistence
- core simulation services
- manufacturing and procurement workflows
- event logging
- Swagger/OpenAPI documentation
- JSON export and full-state import endpoints
- README and `.gitignore`
- backend operations tests

### 9.2 Still incomplete or pending

- final screenshot capture for the report
- final 5-day scenario write-up
- any additional polish the team chooses to add

## 10. Known Limitations

- the active UI is React, not Streamlit, so the original brief and the final implementation differ
- the production model uses one shared capacity pool rather than detailed line-by-line scheduling
- demand generation is intentionally simple
- the repository still contains an old Streamlit prototype that is no longer the primary path
