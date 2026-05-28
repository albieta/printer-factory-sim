from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes import router
from app.services.catalog_service import CatalogService
from app.utils.database import get_db


def make_client(session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_provider_api_catalog_order_and_day_flow(seeded_session: Session) -> None:
    client = make_client(seeded_session)
    control_board = CatalogService(seeded_session).get_product_by_name("Control Board")
    assert control_board is not None

    catalog_response = client.get("/api/catalog")
    assert catalog_response.status_code == 200
    catalog_payload = catalog_response.json()
    assert catalog_payload["schema_version"] == 1
    assert any(
        item["name"] == "Control Board"
        for item in catalog_payload["products"]
    )

    order_response = client.post(
        "/api/orders",
        json={
            "buyer": "manufacturer",
            "product_id": control_board.id,
            "quantity": 50,
        },
    )
    assert order_response.status_code == 201
    order_payload = order_response.json()["order"]
    assert order_payload["status"] == "PENDING"
    assert order_payload["expected_delivery_day"] == 2

    day_response = client.post("/api/day/advance")
    assert day_response.status_code == 200
    assert day_response.json()["current_day"] == 1

    detail_response = client.get(f"/api/orders/{order_payload['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["schema_version"] == 1
