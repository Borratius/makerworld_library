"""Async client for the unofficial, read-only MakerWorld endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout

from .const import (
    API_BASE_URL,
    CLOUD_API_BASE_URL,
    MAX_COLLECTION_ITEMS,
    PAGE_SIZE,
    REQUEST_TIMEOUT,
)
from .exceptions import (
    MakerWorldAuthenticationError,
    MakerWorldConnectionError,
    MakerWorldRateLimitError,
)
from .models import extract_collection_hits

_LOGGER = logging.getLogger(__name__)


class MakerWorldApiClient:
    """Small read-only client; endpoint assumptions live only in this file."""

    def __init__(self, session: ClientSession, access_token: str | None = None) -> None:
        self._session = session
        self._access_token = access_token.strip() if access_token else None

    async def async_get_collection_designs(
        self, collection_id: str, collection_slug: str
    ) -> list[dict[str, Any]]:
        """Fetch all collection rows with bounded pagination."""
        rows: list[dict[str, Any]] = []
        offset = 0
        while offset < MAX_COLLECTION_ITEMS:
            payload = await self._async_get_json(
                f"/favorites/{collection_id}/designs",
                params={
                    "seed": 0,
                    "collectionId": collection_slug,
                    "limit": PAGE_SIZE,
                    "offset": offset,
                },
            )
            page, total = extract_collection_hits(payload)
            rows.extend(page)
            if not page or len(page) < PAGE_SIZE or (total is not None and len(rows) >= total):
                break
            offset += len(page)

        if len(rows) >= MAX_COLLECTION_ITEMS:
            _LOGGER.warning(
                "MakerWorld collection %s reached the safety limit of %s items",
                collection_id,
                MAX_COLLECTION_ITEMS,
            )
        return rows[:MAX_COLLECTION_ITEMS]

    async def async_get_design(self, design_id: int) -> dict[str, Any]:
        """Fetch full model metadata, including print profiles."""
        return await self._async_get_json(f"/design/{int(design_id)}")

    async def async_get_profile_download(
        self, profile_id: int, model_id: str, access_token: str
    ) -> dict[str, Any]:
        """Create the short-lived download URL used by MakerWorld cloud prints."""
        return await self._async_get_json(
            f"/profile/{int(profile_id)}",
            params={"model_id": model_id},
            access_token=access_token,
            base_url=CLOUD_API_BASE_URL,
        )

    async def async_validate_collection(self, collection_id: str, collection_slug: str) -> None:
        """Perform the smallest useful validation request."""
        await self._async_get_json(
            f"/favorites/{collection_id}/designs",
            params={"seed": 0, "collectionId": collection_slug, "limit": 1, "offset": 0},
        )

    async def _async_get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        access_token: str | None = None,
        base_url: str = API_BASE_URL,
    ) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "HomeAssistant-MakerWorldLibrary/0.1 (+read-only)",
        }
        token = access_token or self._access_token
        if token:
            headers["Authorization"] = f"Bearer {token}"

        url = f"{base_url}{path}"
        for attempt in range(3):
            try:
                async with self._session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=ClientTimeout(total=REQUEST_TIMEOUT),
                ) as response:
                    if response.status in (401, 403):
                        raise MakerWorldAuthenticationError(
                            "MakerWorld rejected the configured access token"
                        )
                    if response.status == 429:
                        if attempt < 2:
                            await asyncio.sleep(_retry_delay(response, attempt))
                            continue
                        raise MakerWorldRateLimitError("MakerWorld rate limit reached")
                    if response.status >= 500 and attempt < 2:
                        await asyncio.sleep(2**attempt)
                        continue
                    if response.status >= 400:
                        raise MakerWorldConnectionError(
                            f"MakerWorld returned HTTP {response.status} for {path}"
                        )
                    payload = await response.json(content_type=None)
                    if not isinstance(payload, dict):
                        raise MakerWorldConnectionError(
                            f"MakerWorld returned an unexpected response for {path}"
                        )
                    return payload
            except MakerWorldAuthenticationError:
                raise
            except (ClientError, asyncio.TimeoutError, ValueError) as err:
                if attempt < 2:
                    await asyncio.sleep(2**attempt)
                    continue
                raise MakerWorldConnectionError(
                    f"Could not read MakerWorld endpoint {path}: {type(err).__name__}"
                ) from err

        raise MakerWorldConnectionError(f"Could not read MakerWorld endpoint {path}")


def _retry_delay(response: ClientResponse, attempt: int) -> float:
    try:
        return min(max(float(response.headers.get("Retry-After", 0)), 1), 30)
    except (TypeError, ValueError):
        return float(2**attempt)
