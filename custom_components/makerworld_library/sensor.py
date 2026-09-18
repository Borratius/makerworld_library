"""Sensors for MakerWorld collection models."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MAX_ENTITY_PROFILES
from .coordinator import MakerWorldLibraryCoordinator
from .models import MakerWorldModel


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MakerWorldLibraryCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_design_ids: set[int] = set()

    async_add_entities([MakerWorldCollectionSensor(coordinator, entry)])

    @callback
    def add_new_model_entities() -> None:
        new_ids = set(coordinator.data.models) - known_design_ids
        if not new_ids:
            return
        known_design_ids.update(new_ids)
        async_add_entities(
            MakerWorldModelSensor(coordinator, entry, design_id)
            for design_id in sorted(new_ids)
        )

    add_new_model_entities()
    entry.async_on_unload(coordinator.async_add_listener(add_new_model_entities))


class MakerWorldCollectionSensor(
    CoordinatorEntity[MakerWorldLibraryCoordinator], SensorEntity
):
    """Collection health and item count."""

    _attr_icon = "mdi:bookshelf"
    _attr_has_entity_name = True
    _attr_name = "Models"

    def __init__(self, coordinator: MakerWorldLibraryCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_collection"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.models)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            "collection_id": data.collection_id,
            "collection_name": data.collection_name,
            "collection_url": f"https://makerworld.com/en/collections/{data.collection_slug}",
            "last_successful_sync": data.fetched_at.isoformat(),
            "partial_failure_count": data.partial_failure_count,
            "read_only": True,
        }

    @property
    def device_info(self) -> DeviceInfo:
        data = self.coordinator.data
        return DeviceInfo(
            identifiers={(DOMAIN, data.collection_id)},
            name=data.collection_name,
            manufacturer="MakerWorld (unofficial API)",
            model="Collection",
            configuration_url=f"https://makerworld.com/en/collections/{data.collection_slug}",
        )


class MakerWorldModelSensor(CoordinatorEntity[MakerWorldLibraryCoordinator], SensorEntity):
    """A compact metadata sensor for one model."""

    _attr_icon = "mdi:printer-3d"
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MakerWorldLibraryCoordinator,
        entry: ConfigEntry,
        design_id: int,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self.design_id = design_id
        self._attr_unique_id = f"{entry.entry_id}_{design_id}"

    @property
    def model(self) -> MakerWorldModel | None:
        return self.coordinator.data.models.get(self.design_id)

    @property
    def available(self) -> bool:
        return super().available and self.model is not None

    @property
    def name(self) -> str:
        return self.model.title if self.model else f"MakerWorld {self.design_id}"

    @property
    def native_value(self) -> str:
        model = self.model
        if model is None:
            return "unavailable"
        return "metadata_available" if model.metadata_complete else "partial_metadata"

    @property
    def entity_picture(self) -> str | None:
        return self.model.image_url if self.model else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        model = self.model
        if model is None:
            return {}
        profiles = [
            profile.as_entity_attribute()
            for profile in model.profiles[:MAX_ENTITY_PROFILES]
        ]
        return {
            "title": model.title,
            "design_id": model.design_id,
            "model_id": model.model_id,
            "image_url": model.image_url,
            "creator": model.creator,
            "source_url": model.source_url,
            "profile_count": len(model.profiles),
            "profiles_truncated": len(model.profiles) > MAX_ENTITY_PROFILES,
            "profiles": profiles,
            "materials": list(model.materials),
            "needs_ams": model.needs_ams,
            "p2s_compatible": model.p2s_compatible,
            "readiness": {
                "state": "checked_when_print_is_pressed",
                "reason": "ams_materials_are_matched_immediately_before_cloud_print",
                "metadata_available": model.metadata_complete,
            },
            "read_only": True,
        }

    @property
    def device_info(self) -> DeviceInfo:
        data = self.coordinator.data
        return DeviceInfo(
            identifiers={(DOMAIN, data.collection_id)},
            name=data.collection_name,
            manufacturer="MakerWorld (unofficial API)",
            model="Collection",
            configuration_url=f"https://makerworld.com/en/collections/{data.collection_slug}",
        )
