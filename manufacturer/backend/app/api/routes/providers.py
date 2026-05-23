from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.models import SimulationConfig
from app.schemas.schemas import ProviderUrlUpdate
from app.services.provider_proxy_service import ProviderProxyService
from app.utils.database import get_db

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/")
def list_providers(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """List all configured providers with health status."""
    config = db.query(SimulationConfig).first()
    provider_urls = config.provider_urls or {} if config else {}
    service = ProviderProxyService(provider_urls)
    return service.get_all_providers()


@router.get("/{name}/catalog")
def get_provider_catalog(name: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Proxy catalog from named provider. Returns online: False if offline."""
    config = db.query(SimulationConfig).first()
    provider_urls = config.provider_urls or {} if config else {}
    service = ProviderProxyService(provider_urls)
    catalog = service.get_provider_catalog(name)
    if catalog is None:
        return {"name": name, "online": False, "error": "Provider not found or unavailable"}
    return catalog


@router.get("/{name}/stock")
def get_provider_stock(name: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Proxy stock levels from named provider."""
    config = db.query(SimulationConfig).first()
    provider_urls = config.provider_urls or {} if config else {}
    service = ProviderProxyService(provider_urls)
    stock = service.get_provider_stock(name)
    if stock is None:
        return {"name": name, "online": False, "items": []}
    return stock


@router.get("/{name}/orders")
def get_provider_orders(name: str, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Proxy orders from named provider."""
    config = db.query(SimulationConfig).first()
    provider_urls = config.provider_urls or {} if config else {}
    service = ProviderProxyService(provider_urls)
    orders = service.get_provider_orders(name)
    return orders or []


@router.put("/{name}/url")
def update_provider_url(name: str, payload: ProviderUrlUpdate, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Update provider URL override. Pass empty string to use default from config.json."""
    config = db.query(SimulationConfig).first()
    if not config:
        return {"error": "Configuration not found"}

    if not config.provider_urls:
        config.provider_urls = {}

    if payload.url:
        config.provider_urls[name] = payload.url
    else:
        config.provider_urls.pop(name, None)

    db.commit()
    return {"success": True, "provider": name, "url": payload.url or "using default from config.json"}
