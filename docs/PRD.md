# Product Requirements Document (PRD)
# 3D Printer Production Simulator

## Version: 1.0
**Date:** 2026-03-26
**Status:** Draft for Review

---

## 1. Executive Summary

The 3D Printer Production Simulator is a web-based manufacturing simulation system that models the end-to-end production workflow of a 3D printer factory. It enables users to configure production parameters, manage inventory and orders, execute day-by-day simulations, and analyze operational performance through dashboards and charts.

### Primary Objectives
- Simulate realistic production workflows including material procurement, assembly, and order fulfillment
- Provide an interactive interface for testing different production strategies
- Generate actionable insights through event logging and visual analytics
- Enable state persistence via JSON import/export for scenario comparison

---

## 2. Data Model

### 2.1 Core Entities

#### Product
Represents any item in the system—both finished printer models and raw materials.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique identifier |
| `name` | string | Human-readable name |
| `type` | enum | `PRINTER` or `MATERIAL` |
| `created_at` | datetime | Record creation timestamp |

#### BillOfMaterials (BOM)
Defines the material requirements for producing one unit of a printer model. One-level structure only (no sub-assemblies).

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique identifier |
| `finished_product_id` | FK → Product.id | The printer this BOM defines |
| `material_id` | FK → Product.id | Required raw material |
| `quantity` | decimal | Units of material per finished unit |

#### Supplier
Defines external sources for purchasing raw materials.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique identifier |
| `name` | string | Supplier company name |
| `product_id` | FK → Product.id | Material supplied |
| `unit_cost` | decimal | Cost per unit (base price) |
| `lead_time_days` | integer | Days from order to delivery |
| `quantity_breaks` | JSON | Tiered pricing: `[{qty: 100, price: 9.50}, {qty: 500, price: 8.75}]` |

#### Inventory
Tracks current stock levels of raw materials.

| Field | Type | Description |
|-------|------|-------------|
| `product_id` | FK → Product.id | The material tracked |
| `quantity` | decimal | Current available quantity |
| `last_updated` | datetime | Last modification time |

#### ManufacturingOrder
Represents customer demand for finished printers.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique identifier |
| `product_id` | FK → Product.id | Printer model ordered |
| `quantity` | integer | Number of units requested |
| `status` | enum | `PENDING`, `RELEASED`, `COMPLETED`, `BLOCKED` |
| `created_date` | date | Simulation date when order was generated |
| `released_date` | date | When production started (nullable) |
| `completed_date` | date | When order finished (nullable) |

#### PurchaseOrder
Represents procurement requests to suppliers.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique identifier |
| `supplier_id` | FK → Supplier.id | Vendor placing the order |
| `product_id` | FK → Product.id | Material being ordered |
| `quantity` | integer | Units ordered |
| `issue_date` | date | Order placement date |
| `expected_delivery` | date | Calculated as issue_date + lead_time |
| `actual_delivery` | date | Actual delivery date (nullable) |
| `status` | enum | `PENDING`, `DELIVERED`, `REJECTED` |
| `unit_cost` | decimal | Final cost per unit after quantity breaks |

#### Event
Audit log capturing all significant system actions.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique identifier |
| `event_type` | enum | See event types below |
| `sim_date` | date | Simulation date when event occurred |
| `timestamp` | datetime | Real-time wall clock timestamp |
| `details` | JSON | Event-specific payload |

#### SimulationConfig
System-wide configuration parameters.

| Field | Type | Description |
|-------|------|-------------|
| `warehouse_capacity` | integer | Total storage units available |
| `daily_assembly_hours` | decimal | Production capacity per day |
| `demand_distribution_mean` | float | Mean orders per day |
| `demand_distribution_variance` | float | Variance in daily orders |

### 2.2 Event Types

| Category | Event Type | Trigger Condition |
|----------|------------|-------------------|
| **Manufacturing Orders** | `ORDER_CREATED` | New order generated daily |
| | `ORDER_RELEASED` | Order moved to production |
| | `ORDER_BLOCKED_MATERIALS` | Release failed due to insufficient inventory |
| | `ORDER_STARTED` | Production actually began |
| | `ORDER_COMPLETED` | All units produced |
| **Purchase Orders** | `PO_CREATED` | User created purchase order |
| | `PO_DELIVERED` | Shipment arrived and accepted |
| | `PO_REJECTED_CAPACITY` | Delivery rejected due to warehouse overflow |
| **Inventory / Materials** | `MATERIAL_CONSUMED` | Materials used in production |
| | `INVENTORY_ADDED` | New stock received from supplier |
| **Simulation Control** | `DAY_ADVANCED` | Simulation progressed to next day |
| | `PRODUCTION_BLOCKED_CAPACITY` | No remaining assembly hours today |

---

## 3. System Architecture

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Presentation Layer                       │
│  ┌──────────────────────┐         ┌──────────────────────────┐  │
│  │   Streamlit UI       │◄───────►│     Swagger UI (FastAPI) │  │
│  │   (Dashboard)        │         │     (API Documentation)  │  │
│  └──────────┬───────────┘         └──────────────────────────┘  │
└─────────────┼───────────────────────────────────────────────────┘
              │ REST API (HTTP/JSON)
┌─────────────▼───────────────────────────────────────────────────┐
│                        Application Layer                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              REST API Routes (FastAPI)                   │   │
│  └──────────┬───────────────────────────────────────────────┘   │
│             │                                                   │
│  ┌──────────▼───────────────────────────────────────────────┐   │
│  │            Business Logic Services                       │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │   │
│  │  │ ConfigSvc   │  │ OrderSvc    │  │ ProductionSvc   │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘   │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │   │
│  │  │ SupplierSvc │  │ InventorySvc│  │ SimulationSvc   │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘   │   │
│  └───────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                        Data Access Layer                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  SQLite Database                         │   │
│  │              (via SQLAlchemy / Pydantic)                 │   │
│  └──────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

### 3.2 Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| **Streamlit UI** | Dashboard rendering, user interaction forms, chart visualization |
| **REST API** | HTTP endpoint exposure, request validation, response serialization |
| **ConfigService** | Manage system configuration, validate constraints |
| **OrderService** | Manufacturing order lifecycle management |
| **PurchaseOrderService** | PO creation, delivery scheduling, capacity validation |
| **ProductionService** | Assembly hour allocation, material consumption logic |
| **InventoryService** | Stock level queries, reservation checks, updates |
| **SimulationService** | Daily cycle orchestration, event generation, state transitions |

### 3.3 Daily Execution Flow (Advance Day)

```
┌─────────────────────────────────────────────────────────────┐
│                     Advance Day Button Click                 │
└───────────────────────┬─────────────────────────────────────┘
                        ▼
            ┌───────────────────────────┐
            │ 1. Increment sim_date     │
            └───────────┬───────────────┘
                        ▼
            ┌───────────────────────────┐
            │ 2. Process PO deliveries  │
            │   - Check due dates       │
            │   - Validate capacity     │
            │   - Update inventory      │
            └───────────┬───────────────┘
                        ▼
            ┌───────────────────────────┐
            │ 3. Generate new orders    │
            │   - Random model + qty    │
            │   - Set PENDING status    │
            └───────────┬───────────────┘
                        ▼
            ┌───────────────────────────┐
            │ 4. Execute production     │
            │   - Iterate RELEASED ord. │
            │   - Check materials       │
            │   - Allocate hours        │
            │   - Consume & complete    │
            └───────────┬───────────────┘
                        ▼
            ┌───────────────────────────┐
            │ 5. Log all events         │
            │   - Write to database     │
            │   - Update dashboard      │
            └───────────────────────────┘
```

---

## 4. Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Backend Framework** | FastAPI | Native async support, automatic OpenAPI docs, Pydantic integration |
| **Data Validation** | Pydantic v2 | Type safety, consistent schemas across API and business logic |
| **Frontend** | Streamlit | Rapid prototyping, built-in charting, no frontend expertise required |
| **Database** | SQLite | Zero-config, portable, sufficient for single-user simulation |
| **ORM / DB Access** | SQLAlchemy 2.0 | Type-safe queries, migration support via Alembic |
| **Charts** | Plotly (via Streamlit) | Interactive charts, exports to PNG/HTML |
| **Testing** | pytest + httpx | Standard Python testing, async API test support |
| **Package Manager** | pip / requirements.txt | Simple dependency management |
| **Documentation** | FastAPI auto-docs | Swagger UI at `/docs`, ReDoc at `/redoc` |

### 4.1 Version Requirements

- Python: 3.11+
- FastAPI: 0.104+
- Streamlit: 1.28+
- SQLAlchemy: 2.0+
- Pydantic: 2.0+

---

## 5. REST API Endpoints

### 5.1 Configuration Endpoints

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| GET | `/api/config` | Get full system configuration | — | `SimulationConfig` |
| PUT | `/api/config` | Update system configuration | `SimulationConfigUpdate` | `SimulationConfig` |
| GET | `/api/config/printer-models` | List all printer models | — | `List[PrinterModel]` |
| POST | `/api/config/printer-models` | Add new printer model | `PrinterModelCreate` | `PrinterModel` |
| DELETE | `/api/config/printer-models/{id}` | Remove printer model | — | `204 No Content` |

### 5.2 Material & BOM Endpoints

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| GET | `/api/materials` | List all raw materials | — | `List[Material]` |
| POST | `/api/materials` | Create new material | `MaterialCreate` | `Material` |
| GET | `/api/bom` | List all BOM entries | — | `List[BOMEntry]` |
| POST | `/api/bom` | Add BOM entry | `BOMCreate` | `BOMEntry` |
| DELETE | `/api/bom/{id}` | Remove BOM entry | — | `204 No Content` |

### 5.3 Supplier Endpoints

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| GET | `/api/suppliers` | List all suppliers | — | `List[Supplier]` |
| POST | `/api/suppliers` | Create new supplier | `SupplierCreate` | `Supplier` |
| PUT | `/api/suppliers/{id}` | Update supplier details | `SupplierUpdate` | `Supplier` |
| DELETE | `/api/suppliers/{id}` | Remove supplier | — | `204 No Content` |

### 5.4 Inventory Endpoints

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| GET | `/api/inventory` | Get all inventory levels | — | `List[InventoryLevel]` |
| GET | `/api/inventory/capacity` | Get warehouse capacity usage | — | `CapacityInfo` |
| POST | `/api/inventory/manual-adjust` | Manual inventory adjustment | `ManualAdjust` | `InventoryLevel` |

### 5.5 Manufacturing Order Endpoints

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| GET | `/api/orders/mfg` | List all manufacturing orders | `?status=PENDING` | `List[ManufacturingOrder]` |
| POST | `/api/orders/mfg/release` | Release order(s) to production | `ReleaseRequest` | `BatchReleaseResponse` |
| GET | `/api/orders/mfg/{id}` | Get order details | — | `ManufacturingOrderDetail` |
| GET | `/api/orders/mfg/{id}/requirements` | Get BOM requirements | — | `BOMRequirements` |

### 5.6 Purchase Order Endpoints

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| GET | `/api/orders/purchase` | List all purchase orders | — | `List[PurchaseOrder]` |
| POST | `/api/orders/purchase` | Create new purchase order | `PurchaseOrderCreate` | `PurchaseOrder` |
| GET | `/api/orders/purchase/{id}` | Get PO details | — | `PurchaseOrderDetail` |

### 5.7 Simulation Endpoints

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| GET | `/api/simulation/status` | Get current simulation state | — | `SimulationStatus` |
| POST | `/api/simulation/advance-day` | Execute one simulation day | — | `DayAdvanceResult` |
| POST | `/api/simulation/reset` | Reset simulation to initial state | — | `ResetConfirm` |

### 5.8 Event Log Endpoints

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| GET | `/api/events` | Query event history | `?type=ORDER_CREATED&from_date=...` | `List[Event]` |
| GET | `/api/events/timeseries/{metric}` | Get metrics for charting | — | `TimeSeriesData` |

### 5.9 Import/Export Endpoints

| Method | Endpoint | Description | Request Body | Response |
|--------|----------|-------------|--------------|----------|
| GET | `/api/export/full-state` | Export complete simulation state | — | JSON file download |
| POST | `/api/import/full-state` | Import simulation state | JSON file upload | `ImportResult` |
| GET | `/api/export/inventory-only` | Export inventory snapshot | — | JSON file download |
| GET | `/api/export/events-only` | Export event history | — | JSON file download |

### 5.10 Health & Metadata

| Method | Endpoint | Description | Response |
|--------|----------|-------------|----------|
| GET | `/health` | Health check | `{"status": "ok"}` |
| GET | `/docs` | Swagger UI documentation | HTML interface |
| GET | `/openapi.json` | OpenAPI specification | JSON schema |

---

## 6. User Interface (Streamlit Dashboard)

### 6.1 Layout Structure

```
┌─────────────────────────────────────────────────────────────┐
│  🏭 3D Printer Production Simulator                          │
├──────────────┬──────────────────────────────────────────────┤
│   NAVIGATION │           MAIN CONTENT AREA                  │
│              │                                              │
│  Overview    │  ┌────────────────────────────────────┐     │
│  Orders      │  │  KPI Cards:                        │     │
│  Inventory   │  │  [Pending Orders] [On Hand] [...]  │     │
│  Suppliers   │  └────────────────────────────────────┘     │
│  Production  │                                              │
│  Reports     │  ┌────────────────────────────────────┐     │
│  Settings    │  │  Charts:                           │     │
│              │  │  • Inventory Over Time             │     │
│              │  │  • Production Throughput           │     │
│              │  │  • Orders Created vs Completed     │     │
│              │  └────────────────────────────────────┘     │
│              │                                              │
│              │  ┌────────────────────────────────────┐     │
│              │  │  [📅 Advance Day Button]           │     │
│              │  └────────────────────────────────────┘     │
└──────────────┴──────────────────────────────────────────────┘
```

### 6.2 Page Specifications

| Page | Components |
|------|------------|
| **Overview** | KPI cards, summary charts, advance day button, recent events feed |
| **Orders** | Manufacturing order table, release form, order details panel, BOM requirements viewer |
| **Inventory** | Material stock table, capacity gauge, low-stock warnings, purchase order form |
| **Suppliers** | Supplier list, pricing tier editor, lead time display |
| **Production** | Active orders panel, capacity utilization meter, completion tracking |
| **Reports** | Event log viewer, custom date range charts, export buttons |
| **Settings** | Configuration editor, import/export controls, system reset |

---

## 7. Development Plan

### Phase 1: Foundation (Week 1)
**Goal:** Establish project skeleton with working API and database

| Task ID | Task | Deliverable |
|---------|------|-------------|
| 1.1 | Project setup | Repo structure, virtual environment, requirements.txt |
| 1.2 | Database models | SQLAlchemy entities for all core entities |
| 1.3 | Pydantic schemas | Request/response DTOs for all endpoints |
| 1.4 | Basic CRUD routes | GET/POST for config, materials, printers |
| 1.5 | Seed data script | Initial configuration population |

**Acceptance Criteria:**
- `uvicorn main:app --reload` starts server
- Swagger UI accessible at `/docs`
- Can create/read printer models and materials via API
- SQLite database created with all tables

---

### Phase 2: Core Business Logic (Week 2)
**Goal:** Implement simulation engine and order management

| Task ID | Task | Deliverable |
|---------|------|-------------|
| 2.1 | Inventory service | Stock query, consumption, capacity checks |
| 2.2 | Order service | Manufacturing order lifecycle |
| 2.3 | Purchase order service | PO creation, delivery scheduling |
| 2.4 | Production service | Assembly hour allocation, BOM validation |
| 2.5 | Event logging service | Event generation and storage |

**Acceptance Criteria:**
- Can release manufacturing order (with material check)
- Can create purchase order (with lead time calculation)
- Materials consumed correctly on order start
- Events logged for all operations

---

### Phase 3: Simulation Engine (Week 2-3)
**Goal:** Build day advancement and automated workflows

| Task ID | Task | Deliverable |
|---------|------|-------------|
| 3.1 | Simulation context manager | Track current date, state isolation |
| 3.2 | Daily demand generator | Random order creation with configurable params |
| 3.3 | Delivery processor | PO delivery logic with capacity validation |
| 3.4 | Production executor | Capacity-constrained production run |
| 3.5 | Advance day orchestrator | Sequence all daily operations |

**Acceptance Criteria:**
- `POST /api/simulation/advance-day` executes full cycle
- New orders generated based on mean/variance settings
- POs deliver on expected dates
- Production respects assembly hour limits

---

### Phase 4: Streamlit UI (Week 3-4)
**Goal:** Build interactive dashboard

| Task ID | Task | Deliverable |
|---------|------|-------------|
| 4.1 | Navigation layout | Sidebar with all pages |
| 4.2 | Overview page | KPIs, charts, action buttons |
| 4.3 | Orders page | Table, release form, requirements viewer |
| 4.4 | Inventory page | Stock levels, PO creation form |
| 4.5 | Reports page | Event log, time-series charts |
| 4.6 | Settings page | Config editor, import/export |

**Acceptance Criteria:**
- All pages render without errors
- Forms submit to API and update state
- Charts display live data
- Advance day button visible and functional

---

### Phase 5: Import/Export & Polish (Week 4)
**Goal:** Complete data portability and user experience

| Task ID | Task | Deliverable |
|---------|------|-------------|
| 5.1 | Full state export | JSON containing all simulation data |
| 5.2 | Full state import | Restore simulation from exported JSON |
| 5.3 | Inventory-only export/import | Partial state operations |
| 5.4 | Event history export | Separate event log download |
| 5.5 | Error handling | Graceful failures with user messages |
| 5.6 | Documentation | README, API usage examples |

**Acceptance Criteria:**
- Export produces valid JSON file
- Import restores complete simulation state
- Invalid imports rejected with clear error messages

---

### Phase 6: Testing & Documentation (Week 5)
**Goal:** Ensure reliability and completeness

| Task ID | Task | Deliverable |
|---------|------|-------------|
| 6.1 | Unit tests | Business logic coverage (>70%) |
| 6.2 | API integration tests | All endpoints tested |
| 6.3 | Simulation tests | Day advancement scenarios |
| 6.4 | Load testing | Concurrent API request handling |
| 6.5 | User guide | How-to documentation |
| 6.6 | Final review | Code cleanup, comments, linting |

**Acceptance Criteria:**
- All tests pass (`pytest`)
- Linting clean (`ruff` / `black`)
- Type checking passes (`mypy --strict`)
- README documents setup and usage

---

## 8. Milestone Summary

| Milestone | Description | Target | Status |
|-----------|-------------|--------|--------|
| M1 | Project scaffold, API running | Week 1 | Planned |
| M2 | Core services implemented | Week 2 | Planned |
| M3 | Simulation engine functional | Week 3 | Planned |
| M4 | Complete Streamlit UI | Week 4 | Planned |
| M5 | Import/export complete | Week 4 | Planned |
| M6 | Testing & documentation done | Week 5 | Planned |

---

## 9. Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Scope creep on charting features | Timeline slip | Limit to 3 minimum charts; optional later |
| Complex BOM validation logic | Implementation delays | Keep to one-level BOM only |
| State corruption during import | Data loss | Validate before replace; offer rollback |
| Performance degradation with many events | Slow UI | Implement pagination on event log |

---

## 10. Out of Scope (Future Versions)

- Multi-user support and authentication
- Sub-assembly BOM structures
- Work-in-progress (WIP) tracking
- Advanced scheduling algorithms
- Mobile responsive design
- WebSocket real-time updates
- Multiple simulation runs for scenario comparison

---

## Appendix A: Sample Configuration

```json
{
  "warehouse_capacity": 1000,
  "daily_assembly_hours": 8.0,
  "demand_distribution_mean": 5.0,
  "demand_distribution_variance": 2.0,
  "printer_models": [
    {"name": "Basic300", "assembly_hours": 2.0},
    {"name": "Pro450", "assembly_hours": 4.0},
    {"name": "Elite700", "assembly_hours": 6.0}
  ],
  "materials": [
    {"name": "PLA Filament"},
    {"name": "ABS Filament"},
    {"name": "Aluminum Frame"},
    {"name": "Stepper Motor"}
  ]
}
```

---

*End of PRD*
