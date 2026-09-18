"""One-click cloud print buttons for MakerWorld collection models."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ACCESS_TOKEN, CONF_PRINTER_DEVICE_ID, DOMAIN
from .coordinator import MakerWorldLibraryCoordinator
from .exceptions import MakerWorldError
from .models import MakerWorldModel, PrintProfile

_LOGGER = logging.getLogger(__name__)
BAMBU_DOMAIN = "bambu_lab"
BAMBU_PRINT_SERVICE = "print_project_file"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add a print button when each collection model is discovered."""
    coordinator: MakerWorldLibraryCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_design_ids: set[int] = set()

    @callback
    def add_new_buttons() -> None:
        new_ids = set(coordinator.data.models) - known_design_ids
        if not new_ids:
            return
        known_design_ids.update(new_ids)
        async_add_entities(
            MakerWorldPrintButton(hass, coordinator, entry, design_id)
            for design_id in sorted(new_ids)
        )

    add_new_buttons()
    entry.async_on_unload(coordinator.async_add_listener(add_new_buttons))


class MakerWorldPrintButton(
    CoordinatorEntity[MakerWorldLibraryCoordinator], ButtonEntity
):
    """Start the preferred P2S profile through the Bambu cloud connection."""

    _attr_icon = "mdi:printer-3d-nozzle"
    _attr_has_entity_name = False

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: MakerWorldLibraryCoordinator,
        entry: ConfigEntry,
        design_id: int,
    ) -> None:
        super().__init__(coordinator)
        self.hass = hass
        self.entry = entry
        self.design_id = design_id
        self._attr_unique_id = f"{entry.entry_id}_{design_id}_print"

    @property
    def model(self) -> MakerWorldModel | None:
        return self.coordinator.data.models.get(self.design_id)

    @property
    def name(self) -> str:
        title = self.model.title if self.model else str(self.design_id)
        return f"Print {title}"

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.model is not None
            and self._preferred_profile(self.model) is not None
            and self.hass.services.has_service(BAMBU_DOMAIN, BAMBU_PRINT_SERVICE)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        model = self.model
        profile = self._preferred_profile(model) if model else None
        return {
            "design_id": self.design_id,
            "profile_id": self._print_profile_id(profile) if profile else None,
            "plate": 1,
            "materials": list(profile.materials) if profile else [],
            "p2s_compatible": profile.p2s_compatible if profile else False,
            "cloud_print": True,
        }

    async def async_press(self) -> None:
        """Resolve a fresh URL, map AMS material, and ask ha-bambulab to print."""
        model = self.model
        if model is None:
            raise HomeAssistantError("Dit MakerWorld-model is niet meer beschikbaar")
        profile = self._preferred_profile(model)
        if profile is None:
            raise HomeAssistantError("MakerWorld heeft geen P2S-profiel voor dit model")
        if not model.model_id:
            raise HomeAssistantError("MakerWorld gaf geen intern model-ID terug")

        token, bambu_entry_id = self._cloud_token_and_entry_id()
        if not token:
            raise HomeAssistantError(
                "Geen Bambu-cloudtoken gevonden. Configureer de P2S via Bambu Lab Cloud in Home Assistant."
            )
        mapping = self._ams_mapping(profile, bambu_entry_id)

        try:
            download = await self.coordinator.client.async_get_profile_download(
                self._print_profile_id(profile), model.model_id, token
            )
        except MakerWorldError as err:
            raise HomeAssistantError(
                "MakerWorld kon geen tijdelijke printlink maken; herauthenticeer de Bambu Lab-integratie"
            ) from err

        body = download.get("data") if isinstance(download.get("data"), dict) else download
        signed_url = body.get("url") if isinstance(body, dict) else None
        if not isinstance(signed_url, str) or not signed_url.startswith("https://"):
            raise HomeAssistantError("MakerWorld gaf geen geldige printlink terug")

        printer_device_id = self.entry.data[CONF_PRINTER_DEVICE_ID]
        service_data = {
            "device_id": printer_device_id,
            "filepath": signed_url,
            "plate": 1,
            "timelapse": False,
            "bed_leveling": True,
            "flow_cali": True,
            "vibration_cali": True,
            "layer_inspect": True,
            "use_ams": bool(mapping),
            "ams_mapping": ",".join(str(value) for value in mapping) if mapping else "0",
        }
        _LOGGER.info(
            "Requesting cloud print for MakerWorld design %s, profile %s, plate 1",
            model.design_id,
            self._print_profile_id(profile),
        )
        await self.hass.services.async_call(
            BAMBU_DOMAIN,
            BAMBU_PRINT_SERVICE,
            service_data,
            blocking=True,
        )

    def _cloud_token_and_entry_id(self) -> tuple[str | None, str | None]:
        manual_token = self.entry.data.get(CONF_ACCESS_TOKEN)
        printer_id = self.entry.data[CONF_PRINTER_DEVICE_ID]
        device = dr.async_get(self.hass).async_get(printer_id)
        if device is None:
            return manual_token, None
        for config_entry_id in device.config_entries:
            candidate = self.hass.config_entries.async_get_entry(config_entry_id)
            if candidate is None or candidate.domain != BAMBU_DOMAIN:
                continue
            token = candidate.options.get("auth_token") or candidate.data.get("auth_token")
            return manual_token or token, candidate.entry_id
        return manual_token, None

    def _ams_mapping(self, profile: PrintProfile, bambu_entry_id: str | None) -> list[int]:
        required = list(profile.materials)
        if not required:
            raise HomeAssistantError("Het printprofiel bevat geen bruikbare materiaalgegevens")
        if bambu_entry_id is None:
            raise HomeAssistantError("De gekozen printer hoort niet bij een Bambu Lab-configuratie")

        registry = er.async_get(self.hass)
        trays: list[tuple[str, str]] = []
        for entity in er.async_entries_for_config_entry(registry, bambu_entry_id):
            if entity.domain != "sensor" or entity.platform != BAMBU_DOMAIN:
                continue
            if "ams" not in entity.entity_id or "tray" not in entity.entity_id:
                continue
            state = self.hass.states.get(entity.entity_id)
            if state is None or state.attributes.get("empty") is True:
                continue
            material = state.attributes.get("type") or state.attributes.get("tray_type")
            if material:
                trays.append((entity.entity_id, str(material)))
        trays.sort(key=lambda item: item[0])

        mapping: list[int] = []
        used: set[int] = set()
        for material in required:
            wanted = _normalize_material(material)
            match = next(
                (
                    index
                    for index, (_, loaded) in enumerate(trays)
                    if index not in used and _normalize_material(loaded) == wanted
                ),
                None,
            )
            if match is None:
                raise HomeAssistantError(
                    f"Niet printklaar: geen vrije AMS-slot met materiaal {material} gevonden"
                )
            used.add(match)
            mapping.append(match)
        return mapping

    @staticmethod
    def _preferred_profile(model: MakerWorldModel) -> PrintProfile | None:
        profiles = [profile for profile in model.profiles if profile.p2s_compatible]
        if not profiles:
            return None
        return next((profile for profile in profiles if profile.is_default), profiles[0])

    @staticmethod
    def _print_profile_id(profile: PrintProfile) -> int:
        profile_id = profile.p2s_profile_id or profile.profile_id
        if profile_id is None:
            raise HomeAssistantError("Het P2S-profiel heeft geen profiel-ID")
        return profile_id


def _normalize_material(value: str) -> str:
    """Normalize common MakerWorld/AMS material labels for safe exact matching."""
    cleaned = " ".join(value.upper().replace("_", " ").replace("-", " ").split())
    aliases = {
        "PLA BASIC": "PLA",
        "PLA MATTE": "PLA",
        "PETG BASIC": "PETG",
        "PETG HF": "PETG",
    }
    return aliases.get(cleaned, cleaned)
