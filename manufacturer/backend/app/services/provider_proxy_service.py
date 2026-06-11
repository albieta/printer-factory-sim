from __future__ import annotations

from typing import Any

import httpx


class ProviderProxyService:
    """Proxy requests to external provider services with graceful offline handling."""

    def __init__(self, provider_urls: dict[str, str] | None = None):
        """Initialize with optional provider URL overrides.

        Args:
            provider_urls: Dict mapping provider names to URLs, overrides config.json
        """
        self.provider_urls = provider_urls or {}

    def get_all_providers(self) -> list[dict[str, Any]]:
        """Returns configured providers with online/offline status."""
        from app.utils.app_config import get_configured_providers

        providers = []
        for provider in get_configured_providers():
            provider_name = provider.get("name")
            provider_url = self.provider_urls.get(provider_name) or provider.get("url")
            if not provider_name or not provider_url:
                continue

            online = self._is_provider_online(provider_url)
            providers.append(
                {
                    "name": provider_name,
                    "url": provider_url,
                    "online": online,
                }
            )
        return providers

    def get_provider_catalog(self, provider_name: str) -> dict[str, Any] | None:
        """Proxy GET /api/catalog from named provider.
        Returns None if provider offline or not found."""
        from app.utils.app_config import get_configured_providers

        for provider in get_configured_providers():
            if provider.get("name") != provider_name:
                continue

            provider_url = self.provider_urls.get(provider_name) or provider.get("url")
            if not provider_url:
                return None

            if not self._is_provider_online(provider_url):
                return {"name": provider_name, "url": provider_url, "online": False}

            try:
                with httpx.Client(timeout=3.0) as client:
                    response = client.get(f"{provider_url}/api/catalog")
                    if response.status_code == 200:
                        return response.json()
            except (httpx.RequestError, httpx.TimeoutException):
                pass

            return None

        return None

    def get_provider_stock(self, provider_name: str) -> dict[str, Any] | None:
        """Proxy GET /api/stock from named provider.
        Returns None if provider offline or not found.
        Always returns {"online": bool, "items": [...]} when provider is found."""
        from app.utils.app_config import get_configured_providers

        for provider in get_configured_providers():
            if provider.get("name") != provider_name:
                continue

            provider_url = self.provider_urls.get(provider_name) or provider.get("url")
            if not provider_url:
                return None

            if not self._is_provider_online(provider_url):
                return {"name": provider_name, "online": False, "items": []}

            try:
                with httpx.Client(timeout=3.0) as client:
                    response = client.get(f"{provider_url}/api/stock")
                    if response.status_code == 200:
                        data = response.json()
                        items = data if isinstance(data, list) else data.get("items", [])
                        return {"name": provider_name, "online": True, "items": items}
            except (httpx.RequestError, httpx.TimeoutException):
                pass

            return {"name": provider_name, "online": False, "items": []}

        return None

    def get_provider_orders(self, provider_name: str) -> list[dict[str, Any]] | None:
        """Proxy GET /api/orders from named provider.
        Returns None if provider offline or not found."""
        from app.utils.app_config import get_configured_providers

        for provider in get_configured_providers():
            if provider.get("name") != provider_name:
                continue

            provider_url = self.provider_urls.get(provider_name) or provider.get("url")
            if not provider_url:
                return None

            if not self._is_provider_online(provider_url):
                return []

            try:
                with httpx.Client(timeout=3.0) as client:
                    response = client.get(f"{provider_url}/api/orders")
                    if response.status_code == 200:
                        data = response.json()
                        return data if isinstance(data, list) else data.get("orders", [])
            except (httpx.RequestError, httpx.TimeoutException):
                pass

            return None

        return None

    def _is_provider_online(self, provider_url: str) -> bool:
        """Check if provider is reachable with a GET request to /health."""
        try:
            with httpx.Client(timeout=3.0) as client:
                response = client.get(f"{provider_url}/health")
                return response.status_code == 200
        except (httpx.RequestError, httpx.TimeoutException):
            return False
