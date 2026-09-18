"""Stable, compact data models for the unofficial MakerWorld responses."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


def _first(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return default


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


@dataclass(frozen=True, slots=True)
class PrintProfile:
    """The subset of a MakerWorld print profile useful to Home Assistant."""

    profile_id: int | None
    instance_id: int | None
    title: str
    is_default: bool
    needs_ams: bool | None
    materials: tuple[str, ...]
    plate_count: int | None
    estimated_print_time_s: int | None
    compatible_printers: tuple[str, ...]
    p2s_compatible: bool
    p2s_profile_id: int | None
    p2s_estimated_print_time_s: int | None
    app_can_print: bool | None

    def as_entity_attribute(self) -> dict[str, Any]:
        """Return a recorder-friendly representation with no raw API data."""
        data = asdict(self)
        data["materials"] = list(self.materials)
        data["compatible_printers"] = list(self.compatible_printers)
        return data


@dataclass(frozen=True, slots=True)
class MakerWorldModel:
    """One model in the configured collection."""

    design_id: int
    title: str
    slug: str
    image_url: str | None
    model_id: str | None
    creator: str | None
    profiles: tuple[PrintProfile, ...] = field(default_factory=tuple)
    metadata_complete: bool = True
    metadata_error: str | None = None

    @property
    def source_url(self) -> str:
        suffix = f"-{self.slug}" if self.slug else ""
        return f"https://makerworld.com/en/models/{self.design_id}{suffix}"

    @property
    def materials(self) -> tuple[str, ...]:
        return tuple(sorted({item for profile in self.profiles for item in profile.materials}))

    @property
    def needs_ams(self) -> bool | None:
        values = [profile.needs_ams for profile in self.profiles if profile.needs_ams is not None]
        return any(values) if values else None

    @property
    def p2s_compatible(self) -> bool | None:
        return any(profile.p2s_compatible for profile in self.profiles) if self.profiles else None


@dataclass(frozen=True, slots=True)
class MakerWorldLibraryData:
    """A complete coordinator snapshot."""

    collection_id: str
    collection_name: str
    collection_slug: str
    models: dict[int, MakerWorldModel]
    fetched_at: datetime
    partial_failure_count: int = 0


def extract_collection_hits(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int | None]:
    """Extract collection rows while tolerating common envelope changes."""
    body = _as_dict(payload.get("data")) or payload
    for key in ("hits", "designs", "items", "list"):
        candidate = body.get(key)
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)], _as_int(body.get("total"))
    return [], _as_int(body.get("total"))


def extract_design_id(row: dict[str, Any]) -> int | None:
    """Extract a numeric design identifier from collection rows."""
    nested = _as_dict(row.get("design"))
    return _as_int(_first(row, "designId", "design_id", "id", default=_first(nested, "id", "designId")))


def parse_model(summary: dict[str, Any], detail: dict[str, Any] | None) -> MakerWorldModel:
    """Normalize a collection hit plus optional design detail."""
    source = detail or summary
    design_id = extract_design_id(source) or extract_design_id(summary)
    if design_id is None:
        raise ValueError("MakerWorld model has no numeric design id")

    creator = _as_dict(_first(source, "designCreator", "creator", default={}))
    image_url = _first(source, "coverUrl", "cover", "image", "thumbnail")
    if isinstance(image_url, dict):
        image_url = _first(image_url, "url", "src")

    return MakerWorldModel(
        design_id=design_id,
        title=str(_first(source, "title", "name", default=_first(summary, "title", "name", default=f"Model {design_id}"))),
        slug=str(_first(source, "slug", default=_first(summary, "slug", default=""))),
        image_url=str(image_url) if image_url else None,
        model_id=str(_first(source, "modelId", "model_id")) if _first(source, "modelId", "model_id") else None,
        creator=str(_first(creator, "name", "handle")) if creator else None,
        profiles=tuple(_parse_profile(item) for item in _profile_rows(source)),
        metadata_complete=detail is not None,
        metadata_error=None if detail is not None else "detail_request_failed",
    )


def _profile_rows(detail: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("instances", "printProfiles", "profiles"):
        candidate = detail.get(key)
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
        if isinstance(candidate, dict):
            hits, _ = extract_collection_hits(candidate)
            return hits
    return []


def _parse_profile(raw: dict[str, Any]) -> PrintProfile:
    extension = _as_dict(_first(raw, "extention", "extension", default={}))
    model_info = _as_dict(extension.get("modelInfo"))
    plates = _as_list(model_info.get("plates"))
    compatibility = [_as_dict(model_info.get("compatibility")), *[_as_dict(v) for v in _as_list(model_info.get("otherCompatibility"))]]
    alternates = [_as_dict(v) for v in _as_list(extension.get("otherCompatibilityModelInfo"))]
    p2s_alternate = next((v for v in alternates if _printer_name(v).casefold() == "p2s"), {})

    printer_names = {_printer_name(item) for item in compatibility if _printer_name(item)}
    printer_names.update(_printer_name(item) for item in alternates if _printer_name(item))
    p2s_compatible = any(name.casefold() == "p2s" for name in printer_names)

    filaments = _as_list(raw.get("instanceFilaments"))
    if not filaments and p2s_alternate:
        filaments = _as_list(p2s_alternate.get("instanceFilaments"))
    materials = tuple(sorted({str(_first(_as_dict(item), "type", "material", "name")) for item in filaments if _first(_as_dict(item), "type", "material", "name")}))

    p2s_model_info = _as_dict(p2s_alternate.get("modelInfo"))
    p2s_plates = _as_list(p2s_model_info.get("plates"))
    p2s_prediction = _as_int(p2s_alternate.get("prediction"))
    if p2s_prediction is None and p2s_plates:
        p2s_prediction = sum(filter(None, (_as_int(_as_dict(plate).get("prediction")) for plate in p2s_plates))) or None

    prediction = _as_int(_first(raw, "prediction", "estimatedPrintTime", "printTime"))
    if prediction is None and plates:
        prediction = sum(filter(None, (_as_int(_as_dict(plate).get("prediction")) for plate in plates))) or None

    return PrintProfile(
        profile_id=_as_int(_first(raw, "profileId", "profile_id")),
        instance_id=_as_int(_first(raw, "id", "instanceId", "instance_id")),
        title=str(_first(raw, "title", "name", default="Print profile")),
        is_default=bool(_first(raw, "isDefault", "default", default=False)),
        needs_ams=_as_bool(_first(raw, "needAms", "needsAms", "requiresAms")),
        materials=materials,
        plate_count=len(plates) if plates else _as_int(_first(raw, "plateCount", "plate_count")),
        estimated_print_time_s=prediction,
        compatible_printers=tuple(sorted(printer_names)),
        p2s_compatible=p2s_compatible,
        p2s_profile_id=_as_int(_first(p2s_alternate, "profileId", "profile_id")),
        p2s_estimated_print_time_s=p2s_prediction,
        app_can_print=_as_bool(_first(raw, "appCanPrint", "printable")),
    )


def _printer_name(raw: dict[str, Any]) -> str:
    return str(_first(raw, "devProductName", "productName", "name", default=""))
