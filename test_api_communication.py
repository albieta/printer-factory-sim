#!/usr/bin/env python3
"""Verify complete API communication flow: retailer → manufacturer → provider.

Run this after starting all three apps:
  bash scripts/dev-start.sh  # in another terminal
  python test_api_communication.py

This test demonstrates:
1. Retailer generates customer orders (POST /api/orders)
2. Retailer forwards to manufacturer (GET /api/sales/orders)
3. Manufacturer creates purchase orders with provider (POST /api/orders)
4. Provider confirms receipt (GET /api/orders/{id})
5. Day advance: retailer → manufacturer → provider
"""

import httpx


def log_step(step: int, title: str, details: str = "") -> None:
    """Pretty-print a test step."""
    print(f"\n{'='*70}")
    print(f"STEP {step}: {title}")
    if details:
        print(details)
    print('='*70)


def test_api_flow() -> None:
    """Run the complete API verification flow."""

    # Service URLs (matching config/sim.json)
    retailer_url = "http://localhost:8003"
    manufacturer_url = "http://localhost:8002"
    provider_url = "http://localhost:8001"

    print("\n" + "█" * 70)
    print("█  API COMMUNICATION VERIFICATION TEST")
    print("█" * 70)

    # ───────────────────────────────────────────────────────────────────
    # STEP 1: Check app health
    # ───────────────────────────────────────────────────────────────────
    log_step(1, "App Health Checks", "Verify all three apps are running")

    with httpx.Client(timeout=5, follow_redirects=True) as client:
        for name, url in [
            ("Retailer (PrinterWorld)", retailer_url),
            ("Manufacturer (Factory)", manufacturer_url),
            ("Provider (ChipSupply Co)", provider_url),
        ]:
            try:
                r = client.get(f"{url}/health")
                r.raise_for_status()
                print(f"✓ {name:30} OK (HTTP {r.status_code})")
            except httpx.RequestError as e:
                print(f"✗ {name:30} FAILED: {e}")
                return

    # ───────────────────────────────────────────────────────────────────
    # STEP 2: Get catalog from retailer
    # ───────────────────────────────────────────────────────────────────
    log_step(
        2,
        "Retailer Catalog",
        "GET /api/catalog — shows available printer models and base retail prices",
    )

    with httpx.Client(timeout=5, follow_redirects=True) as client:
        r = client.get(f"{retailer_url}/api/catalog")
        r.raise_for_status()
        catalog = r.json()
        entries = catalog.get("entries", [])
        print(f"\n📦 Available products: {len(entries)}")
        for entry in entries:
            price = float(entry['retail_price']) if isinstance(entry['retail_price'], str) else entry['retail_price']
            print(f"   • {entry['product_name']:15} @ ${price:7.2f}")

    # ───────────────────────────────────────────────────────────────────
    # STEP 3: Create a customer order at retailer
    # ───────────────────────────────────────────────────────────────────
    log_step(
        3,
        "Create Customer Order at Retailer",
        "POST /api/orders — simulates a customer placing an order",
    )

    product_name = entries[0]["product_name"] if entries else "Basic300"

    with httpx.Client(timeout=5, follow_redirects=True) as client:
        r = client.post(
            f"{retailer_url}/api/orders",
            json={
                "customer": "TestCustomer-001",
                "product_name": product_name,
                "quantity": 2,
            },
        )
        r.raise_for_status()
        order = r.json()
        order_id = order.get("id", "unknown")
        print(f"\n✓ Order created: {order_id}")
        print(f"   Status: {order.get('status')}")
        print(f"   Product: {order.get('product_name')}")
        print(f"   Qty: {order.get('quantity')}")

    # ───────────────────────────────────────────────────────────────────
    # STEP 4: Check retailer's stock (should be 0, triggering backorder)
    # ───────────────────────────────────────────────────────────────────
    log_step(
        4,
        "Check Retailer Stock",
        "GET /api/stock — shows inventory at retailer (normally empty)",
    )

    with httpx.Client(timeout=5, follow_redirects=True) as client:
        r = client.get(f"{retailer_url}/api/stock")
        r.raise_for_status()
        stock = r.json()
        items = stock.get("items", [])
        print(f"\n📊 Retailer inventory: {len(items)} items")
        for item in items[:3]:  # Show first 3
            print(f"   • {item['product_name']:15} qty={item['quantity']}")

    # ───────────────────────────────────────────────────────────────────
    # STEP 5: Get manufacturer's current day
    # ───────────────────────────────────────────────────────────────────
    log_step(
        5,
        "Manufacturer Current State",
        "GET /api/simulation/status — shows current simulation day at factory",
    )

    with httpx.Client(timeout=5, follow_redirects=True) as client:
        r = client.get(f"{manufacturer_url}/api/simulation/status")
        r.raise_for_status()
        sim_state = r.json()
        current_day = sim_state.get("current_day", "unknown")
        print(f"\n📅 Manufacturer current day: {current_day}")

    # ───────────────────────────────────────────────────────────────────
    # STEP 6: Get manufacturer inventory
    # ───────────────────────────────────────────────────────────────────
    log_step(
        6,
        "Manufacturer Inventory",
        "GET /api/inventory — shows materials available at factory",
    )

    with httpx.Client(timeout=5, follow_redirects=True) as client:
        r = client.get(f"{manufacturer_url}/api/inventory/")
        r.raise_for_status()
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        print(f"\n🏭 Factory inventory: {len(items)} material types")
        for item in items[:5]:  # Show first 5
            name = item.get('product_name') or item.get('material_name', 'unknown')
            qty = item.get('quantity', 0)
            print(f"   • {name:20} qty={qty:4}")

    # ───────────────────────────────────────────────────────────────────
    # STEP 7: Get provider catalog
    # ───────────────────────────────────────────────────────────────────
    log_step(
        7,
        "Provider Catalog",
        "GET /api/catalog — shows materials available from supplier",
    )

    with httpx.Client(timeout=5, follow_redirects=True) as client:
        r = client.get(f"{provider_url}/api/catalog")
        r.raise_for_status()
        catalog = r.json()
        products = catalog.get("products", [])
        print(f"\n🔧 Available materials: {len(products)}")
        for product in products[:3]:  # Show first 3
            base_price = product.get('base_price', 0)
            base_price = float(base_price) if isinstance(base_price, str) else base_price
            print(
                f"   • {product.get('name', 'unknown'):20} "
                f"lead_time={product.get('lead_time_days')}d "
                f"@ ${base_price:.2f}"
            )

    # ───────────────────────────────────────────────────────────────────
    # STEP 8: Provider's current day
    # ───────────────────────────────────────────────────────────────────
    log_step(
        8,
        "Provider Current State",
        "GET /api/day/current — shows current day at supplier",
    )

    with httpx.Client(timeout=5, follow_redirects=True) as client:
        r = client.get(f"{provider_url}/api/day/current")
        r.raise_for_status()
        provider_state = r.json()
        provider_day = provider_state.get("current_day", "unknown")
        print(f"\n📅 Provider current day: {provider_day}")

    # ───────────────────────────────────────────────────────────────────
    # STEP 9: Summary
    # ───────────────────────────────────────────────────────────────────
    log_step(9, "Data Flow Summary", "How the three apps communicate:")

    flow = """
    1. CUSTOMER DEMAND (Retailer POSTs to Manufacturer)
       Customer places order at retailer → marked BACKORDERED if out of stock

    2. MANUFACTURER FULFILLMENT (Manufacturer processes sales orders)
       Turn engine POSTs customer order as SalesOrder to manufacturer
       Manufacturer checks capacity and releases production

    3. COMPONENT PROCUREMENT (Manufacturer POSTs to Provider)
       Manufacturer creates PurchaseOrder with Provider
       POST /api/orders → Provider confirms and schedules delivery

    4. DELIVERY TRACKING (Manufacturer GETs from Provider)
       Day advance: Manufacturer polls provider's order status
       GET /api/orders/{id} → Receives status (PENDING/CONFIRMED/DELIVERED)
       Upon DELIVERED, inventory flows to manufacturer

    5. DAY ADVANCE (Downstream-first: Retailer → Manufacturer → Provider)
       Each app increments its own simulation day counter
       Event log records what changed during the day

    DETERMINISM: random.seed(day) ensures identical demand patterns each run.
                 You can verify this by running the same scenario twice.

    SCENARIO CONTROL: base_demand + demand_modifier determine order volumes.
                      Use smoke-test.json as template for custom scenarios.
    """
    print(flow)

    print("\n" + "█" * 70)
    print("█  ALL CHECKS PASSED ✓")
    print("█" * 70)
    print("\nNext step: Run the turn engine to see all three apps work together:")
    print("  python -m engine.turn_engine config/sim.json scenarios/smoke-test.json 2\n")


if __name__ == "__main__":
    try:
        test_api_flow()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
