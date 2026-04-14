# 🏭 3D Printer Production Simulator

A web-based manufacturing simulation system that models the end-to-end production workflow of a 3D printer factory. Configure production parameters, manage inventory and orders, execute day-by-day simulations, and analyze operational performance through dashboards and charts.

## Features

- **Production Simulation**: Day-by-day simulation of manufacturing workflows
- **Order Management**: Manufacturing order lifecycle with material availability checks
- **Inventory Tracking**: Real-time stock levels and warehouse capacity management
- **Supplier Management**: Purchase orders with tiered pricing and lead times
- **Event Logging**: Complete audit trail of all simulation events
- **Interactive Dashboard**: Streamlit-based UI with real-time charts and KPIs
- **REST API**: FastAPI backend with automatic Swagger documentation
- **Data Portability**: JSON import/export for scenario comparison

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend Framework | FastAPI 0.104+ |
| Data Validation | Pydantic v2 |
| Frontend | Streamlit 1.28+ |
| Database | SQLite |
| ORM | SQLAlchemy 2.0+ |
| Charts | Plotly |
| Testing | pytest + httpx |

## Quick Start

### Prerequisites

- Python 3.11+
- pip

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd printer-factory-sim
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Seed the database with initial data**
   ```bash
   cd backend
   python scripts/seed_data.py
   ```

5. **Start the FastAPI backend**
   ```bash
   uvicorn main:app --reload --port 8000
   ```

6. **Start the Streamlit dashboard** (in a new terminal)
   ```bash
   cd backend
   streamlit run app/ui/dashboard.py
   ```

7. **Access the applications**
   - Streamlit Dashboard: http://localhost:8501
   - FastAPI Swagger UI: http://localhost:8000/docs
   - FastAPI ReDoc: http://localhost:8000/redoc

## Project Structure

```
printer-factory-sim/
├── backend/
│   ├── main.py                 # FastAPI application entry point
│   ├── app/
│   │   ├── api/
│   │   │   └── routes/         # API route handlers
│   │   │       ├── config.py
│   │   │       ├── materials.py
│   │   │       ├── suppliers.py
│   │   │       ├── inventory.py
│   │   │       ├── orders.py
│   │   │       ├── purchase_orders.py
│   │   │       ├── simulation.py
│   │   │       ├── events.py
│   │   │       └── import_export.py
│   │   ├── models/
│   │   │   └── models.py       # SQLAlchemy database models
│   │   ├── schemas/
│   │   │   └── schemas.py      # Pydantic request/response schemas
│   │   ├── services/
│   │   │   ├── config_service.py
│   │   │   ├── inventory_service.py
│   │   │   ├── order_service.py
│   │   │   ├── supplier_service.py
│   │   │   ├── production_service.py
│   │   │   ├── simulation_service.py
│   │   │   └── event_service.py
│   │   ├── ui/
│   │   │   └── dashboard.py    # Streamlit dashboard
│   │   └── utils/
│   │       └── database.py     # Database configuration
│   ├── scripts/
│   │   └── seed_data.py        # Database seeding script
│   └── tests/                  # Test files
├── requirements.txt
├── README.md
└── PRD.md
```

## API Endpoints

### Configuration
- `GET /api/config` - Get system configuration
- `PUT /api/config` - Update system configuration
- `GET /api/config/printer-models` - List printer models
- `POST /api/config/printer-models` - Create printer model
- `DELETE /api/config/printer-models/{id}` - Delete printer model

### Materials & BOM
- `GET /api/materials` - List materials
- `POST /api/materials` - Create material
- `GET /api/bom` - List BOM entries
- `POST /api/bom` - Create BOM entry
- `DELETE /api/bom/{id}` - Delete BOM entry

### Suppliers
- `GET /api/suppliers` - List suppliers
- `POST /api/suppliers` - Create supplier
- `PUT /api/suppliers/{id}` - Update supplier
- `DELETE /api/suppliers/{id}` - Delete supplier

### Inventory
- `GET /api/inventory` - Get inventory levels
- `GET /api/inventory/capacity` - Get capacity usage
- `POST /api/inventory/manual-adjust` - Manual adjustment

### Orders
- `GET /api/orders/mfg` - List manufacturing orders
- `POST /api/orders/mfg/release` - Release orders to production
- `GET /api/orders/mfg/{id}` - Get order details
- `GET /api/orders/mfg/{id}/requirements` - Get BOM requirements
- `GET /api/orders/purchase` - List purchase orders
- `POST /api/orders/purchase` - Create purchase order

### Simulation
- `GET /api/simulation/status` - Get simulation status
- `POST /api/simulation/advance-day` - Advance one simulation day
- `POST /api/simulation/reset` - Reset simulation

### Events
- `GET /api/events` - Query event history
- `GET /api/events/timeseries/{metric}` - Get time series data

### Import/Export
- `GET /api/export/full-state` - Export full simulation state
- `POST /api/import/full-state` - Import simulation state
- `GET /api/export/inventory-only` - Export inventory
- `GET /api/export/events-only` - Export events

## Usage Guide

### Running a Simulation

1. **Start with seed data**: The database comes pre-configured with:
   - 3 printer models (Basic300, Pro450, Elite700)
   - 6 raw materials
   - 6 suppliers with tiered pricing
   - Initial inventory stock

2. **Advance the simulation day by day**:
   - Click "Advance Day" in the Streamlit dashboard
   - Or call `POST /api/simulation/advance-day`

3. **Each day the simulation**:
   - Processes purchase order deliveries
   - Generates new manufacturing orders (based on demand distribution)
   - Executes production within assembly hour limits
   - Logs all events

4. **Monitor progress**:
   - View KPIs on the Overview page
   - Check charts for production trends
   - Review event logs for detailed history

### Managing Orders

- **Manufacturing Orders**: Automatically generated daily or manually created
- **Release Orders**: Select pending orders and release them to production
- **Material Checks**: System validates material availability before release
- **Production**: Released orders are processed within daily assembly hour limits

### Managing Inventory

- **Automatic Updates**: Inventory changes with PO deliveries and production consumption
- **Capacity Limits**: Warehouse capacity prevents overstocking
- **Manual Adjustments**: Use the manual-adjust endpoint for corrections
- **Low Stock Warnings**: Monitor capacity gauge on Inventory page

### Purchase Orders

- **Create POs**: Select supplier and quantity, system calculates pricing
- **Tiered Pricing**: Larger quantities get better unit costs
- **Lead Times**: Deliveries arrive after supplier-specific lead time days
- **Capacity Checks**: Deliveries rejected if warehouse is full

## Development

### Running Tests

```bash
cd backend
pytest
```

### Code Linting

```bash
ruff check .
```

### Type Checking

```bash
mypy --strict .
```

## Configuration

The simulation is configured via `SimulationConfig` with these parameters:

- **warehouse_capacity**: Total storage units (default: 1000)
- **daily_assembly_hours**: Production capacity per day (default: 8.0)
- **demand_distribution_mean**: Mean daily orders (default: 5.0)
- **demand_distribution_variance**: Variance in daily orders (default: 2.0)

Update configuration via:
- Streamlit Settings page
- `PUT /api/config` endpoint
- Direct database editing

## Data Model

### Core Entities

- **Product**: Printer models and raw materials
- **BillOfMaterials (BOM)**: Material requirements per printer
- **Supplier**: External sources for materials with pricing
- **Inventory**: Current stock levels
- **ManufacturingOrder**: Customer orders for printers
- **PurchaseOrder**: Procurement requests to suppliers
- **Event**: Audit log of all system actions
- **SimulationConfig**: System-wide parameters

See `PRD.md` for complete data model specifications.

## Event Types

The system logs these event types:

- **ORDER_CREATED**: New manufacturing order generated
- **ORDER_RELEASED**: Order moved to production
- **ORDER_BLOCKED_MATERIALS**: Release failed due to insufficient materials
- **ORDER_STARTED**: Production began
- **ORDER_COMPLETED**: All units produced
- **PO_CREATED**: Purchase order created
- **PO_DELIVERED**: Shipment arrived
- **PO_REJECTED_CAPACITY**: Delivery rejected (warehouse full)
- **MATERIAL_CONSUMED**: Materials used in production
- **INVENTORY_ADDED**: New stock received
- **DAY_ADVANCED**: Simulation progressed
- **PRODUCTION_BLOCKED_CAPACITY**: No assembly hours remaining

## Troubleshooting

### API won't start
- Ensure port 8000 is available
- Check that all dependencies are installed: `pip install -r requirements.txt`
- Verify SQLite3 is available in your Python installation

### Streamlit dashboard won't load
- Ensure port 8501 is available
- Verify the backend is running on port 8000
- Check `API_BASE_URL` in `dashboard.py` matches your backend URL

### Database errors
- Run the seed script: `python scripts/seed_data.py`
- Delete the existing database file and re-run the seed script

## License

This project is for educational and demonstration purposes.

## Contributing

Contributions are welcome! Please read the PRD.md for complete specifications before contributing.
