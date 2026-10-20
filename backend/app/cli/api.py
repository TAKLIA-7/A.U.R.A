"""Small API client used by the AURA terminal interface.

The TUI deliberately talks to the same HTTP boundary as the web client.  It
does not import or call policy, JEV, or executor functions directly.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


class AuraApiError(RuntimeError):
    """An API response that the terminal UI can show safely."""


class AuraApiClient:
    def __init__(self, base_url: str | None = None, transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = (base_url or os.getenv("AURA_API_URL", "http://127.0.0.1:8000")).rstrip("/")
        self._transport = transport

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=180, transport=self._transport) as client:
                response = await client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            api_url = httpx.URL(self.base_url)
            endpoint = f"{api_url.scheme}://{api_url.host}"
            if api_url.port is not None:
                endpoint += f":{api_url.port}"
            raise AuraApiError(
                f"Cannot reach the AURA API at {endpoint}. Start the backend with "
                "`uvicorn backend.app.main:app --reload`, or set AURA_API_URL if it runs "
                f"elsewhere. Connection error: {type(exc).__name__}."
            ) from exc
        if response.is_error:
            try:
                message = response.json().get("detail", response.text)
            except ValueError:
                message = response.text
            raise AuraApiError(f"API {response.status_code}: {message}")
        return response.json()

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/api/health")

    async def summary(self) -> dict[str, Any]:
        return await self._request("GET", "/api/monitoring/summary", params={"time_range": "24h"})

    async def actions(self) -> dict[str, Any]:
        return await self._request("GET", "/api/actions", params={"limit": 100, "time_range": "all"})

    async def logs(self, search: str = "") -> dict[str, Any]:
        params: dict[str, Any] = {"limit": 100, "time_range": "all", "sort": "desc"}
        if search.strip():
            params["search"] = search.strip()
        return await self._request("GET", "/api/agent-logs", params=params)

    async def log_detail(self, event_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/agent-logs/{event_id}")

    async def run_prompt(self, prompt: str, trace_id: str | None = None) -> dict[str, Any]:
        headers = {"X-Aura-Trace-Id": trace_id} if trace_id else None
        return await self._request(
            "POST",
            "/api/agent/run",
            json={"prompt": prompt, "mode": "aura"},
            headers=headers,
        )
