"""Privacy-safe diagnostics for MakerWorld Library."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ACCESS_TOKEN, DOMAIN
from .coordinator import MakerWorldLibraryCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics without tokens or raw API payloads."""
    coordinator: MakerWorldLibraryCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data
    config = dict(entry.data)
    if CONF_ACCESS_TOKEN in config:
        config[CONF_ACCESS_TOKEN] = "**REDACTED**"
    return {
        "config_entry": config,
        "options": dict(entry.options),
        "last_update_success": coordinator.last_update_success,
        "collection": {
            "id": data.collection_id,
            "slug": data.collection_slug,
            "model_count": len(data.models),
            "partial_failure_count": data.partial_failure_count,
            "fetched_at": data.fetched_at.isoformat(),
            "models": [
                {
                    "design_id": model.design_id,
                    "profile_count": len(model.profiles),
                    "metadata_complete": model.metadata_complete,
                }
                for model in data.models.values()
            ],
        },
    }
