"""One coordinated poll for a MakerWorld collection."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import MakerWorldApiClient
from .const import (
    CONF_COLLECTION_ID,
    CONF_COLLECTION_SLUG,
    CONF_SCAN_INTERVAL,
    DEFAULT_COLLECTION_NAME,
    DEFAULT_SCAN_INTERVAL,
    MAX_PARALLEL_DETAIL_REQUESTS,
)
from .exceptions import MakerWorldAuthenticationError, MakerWorldError
from .models import (
    MakerWorldLibraryData,
    MakerWorldModel,
    extract_design_id,
    parse_model,
)

_LOGGER = logging.getLogger(__name__)


class MakerWorldLibraryCoordinator(DataUpdateCoordinator[MakerWorldLibraryData]):
    """Fetch collection and model details without duplicating requests per entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: MakerWorldApiClient,
    ) -> None:
        interval = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=f"MakerWorld collection {entry.data[CONF_COLLECTION_ID]}",
            update_interval=timedelta(minutes=interval),
            always_update=True,
        )
        self.entry = entry
        self.client = client

    async def _async_update_data(self) -> MakerWorldLibraryData:
        collection_id = str(self.entry.data[CONF_COLLECTION_ID])
        collection_slug = str(self.entry.data[CONF_COLLECTION_SLUG])
        try:
            summaries = await self.client.async_get_collection_designs(
                collection_id, collection_slug
            )
            models, failures = await self._async_fetch_models(summaries)
        except MakerWorldAuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except MakerWorldError as err:
            raise UpdateFailed(str(err)) from err

        _LOGGER.debug(
            "Updated MakerWorld collection %s: %s models, %s partial failures",
            collection_id,
            len(models),
            failures,
        )
        return MakerWorldLibraryData(
            collection_id=collection_id,
            collection_name=DEFAULT_COLLECTION_NAME,
            collection_slug=collection_slug,
            models={model.design_id: model for model in models},
            fetched_at=dt_util.utcnow(),
            partial_failure_count=failures,
        )

    async def _async_fetch_models(
        self, summaries: list[dict]
    ) -> tuple[list[MakerWorldModel], int]:
        semaphore = asyncio.Semaphore(MAX_PARALLEL_DETAIL_REQUESTS)

        async def fetch(summary: dict) -> MakerWorldModel | None:
            design_id = extract_design_id(summary)
            if design_id is None:
                _LOGGER.warning("Skipping a MakerWorld collection row without design id")
                return None
            try:
                async with semaphore:
                    detail = await self.client.async_get_design(design_id)
                return parse_model(summary, detail)
            except MakerWorldAuthenticationError:
                raise
            except (MakerWorldError, ValueError) as err:
                _LOGGER.warning(
                    "Could not refresh details for MakerWorld design %s; keeping summary metadata (%s)",
                    design_id,
                    type(err).__name__,
                )
                return parse_model(summary, None)

        results = await asyncio.gather(*(fetch(summary) for summary in summaries))
        models = [model for model in results if model is not None]
        failures = sum(not model.metadata_complete for model in models)
        return models, failures
