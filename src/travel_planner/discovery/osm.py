"""Small, read-only OpenStreetMap discovery queries for Japanese trip planning."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal, Protocol

import requests

from travel_planner.discovery.models import DiscoveryCandidate
from travel_planner.geo import distance_km

OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
OSM_LICENCE = "OpenStreetMap contributors, ODbL 1.0"
DiscoveryKind = Literal["onsen", "ryokan", "traditional_inn", "sight"]

_FILTERS: dict[DiscoveryKind, tuple[str, ...]] = {
    "onsen": (
        '["amenity"="public_bath"]',
        '["amenity"="spa"]',
        '["natural"="hot_spring"]',
    ),
    "ryokan": (
        '["tourism"="hotel"]',
        '["tourism"="guest_house"]',
        '["guest_house"="ryokan"]',
    ),
    "traditional_inn": (
        '["tourism"~"guest_house|hotel"]["name"~"民宿|宿坊"]',
        '["tourism"~"guest_house|hotel"]["name:ja"~"民宿|宿坊"]',
        '["amenity"="place_of_worship"]["name"~"宿坊"]',
        '["amenity"="place_of_worship"]["name:ja"~"宿坊"]',
    ),
    "sight": (
        '["tourism"~"attraction|museum|gallery|theme_park|viewpoint"]',
        "[historic]",
        '["amenity"="place_of_worship"]',
        '["leisure"="park"]',
    ),
}


class OSMDiscoveryError(RuntimeError):
    """The public Overpass service did not return usable discovery data."""


class _OverpassResponse(Protocol):
    def raise_for_status(self) -> None: ...

    def json(self) -> Any: ...


class OverpassClient(Protocol):
    def post(
        self,
        url: str,
        *,
        data: dict[str, str],
        headers: dict[str, str],
        timeout: float,
    ) -> _OverpassResponse: ...


def build_query(kind: DiscoveryKind, lat: float, lng: float, radius_m: int) -> str:
    """Build a bounded, tag-only query suitable for an interactive request."""
    if kind not in _FILTERS:
        raise ValueError(f"kind={kind!r} must be one of {', '.join(sorted(_FILTERS))}")
    if not 100 <= radius_m <= 15_000:
        raise ValueError("radius_m must be between 100 and 15000")
    clauses = "\n".join(
        f"  nwr(around:{radius_m},{lat:.6f},{lng:.6f}){tag_filter};"
        for tag_filter in _FILTERS[kind]
    )
    return f"[out:json][timeout:25];\n(\n{clauses}\n);\nout center tags;"


def search_nearby(
    kind: DiscoveryKind,
    *,
    lat: float,
    lng: float,
    radius_m: int = 4_000,
    limit: int = 20,
    client: OverpassClient | None = None,
) -> list[DiscoveryCandidate]:
    """Return named, mappable OSM candidates nearest to a supplied centre."""
    query = build_query(kind, lat, lng, radius_m)
    session = client or requests.Session()
    endpoints = (OVERPASS_URLS[0],) if client else OVERPASS_URLS
    errors: list[str] = []
    raw: Any = None
    for endpoint in endpoints:
        try:
            response = session.post(
                endpoint,
                data={"data": query},
                headers={"User-Agent": "travel-planner/0.1 personal-trip-planner"},
                timeout=35,
            )
            response.raise_for_status()
            raw = response.json()
            break
        except (requests.RequestException, ValueError) as error:
            errors.append(f"{endpoint}: {type(error).__name__}: {error}")
    else:
        raise OSMDiscoveryError("OpenStreetMap discovery failed: " + " | ".join(errors))

    elements = raw.get("elements") if isinstance(raw, dict) else None
    if not isinstance(elements, list):
        raise OSMDiscoveryError("OpenStreetMap discovery returned no element list")
    candidates = [candidate for element in elements if (candidate := _candidate(element, lat, lng))]
    candidates.sort(
        key=lambda candidate: candidate.distance_km
        if candidate.distance_km is not None
        else float("inf")
    )
    return candidates[: min(max(limit, 1), 50)]


def _candidate(raw: Any, centre_lat: float, centre_lng: float) -> DiscoveryCandidate | None:
    if not isinstance(raw, dict):
        return None
    osm_type, osm_id = raw.get("type"), raw.get("id")
    tags = raw.get("tags")
    if not isinstance(osm_type, str) or not isinstance(osm_id, int) or not isinstance(tags, dict):
        return None
    lat, lng = _coordinates(raw)
    if lat is None or lng is None:
        return None
    name = _text(tags, "name:en") or _text(tags, "name") or _text(tags, "name:ja")
    if not name:
        return None
    local_name = _text(tags, "name:ja")
    source_id = f"{osm_type}/{osm_id}"
    return DiscoveryCandidate(
        source="openstreetmap",
        source_id=source_id,
        source_url=f"https://www.openstreetmap.org/{source_id}",
        licence=OSM_LICENCE,
        name=name,
        name_local=local_name if local_name != name else None,
        category=_category(tags),
        lat=lat,
        lng=lng,
        address=_address(tags),
        website=_text(tags, "website") or _text(tags, "contact:website") or _text(tags, "url"),
        opening_hours=_text(tags, "opening_hours"),
        tags=_tags(tags),
        distance_km=distance_km(centre_lat, centre_lng, lat, lng),
    )


def _coordinates(raw: dict[str, Any]) -> tuple[float | None, float | None]:
    lat, lng = raw.get("lat"), raw.get("lon")
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        return float(lat), float(lng)
    center = raw.get("center")
    if isinstance(center, dict):
        lat, lng = center.get("lat"), center.get("lon")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            return float(lat), float(lng)
    return None, None


def _text(tags: dict[str, Any], key: str) -> str | None:
    value = tags.get(key)
    return str(value).strip() if isinstance(value, str) and value.strip() else None


def _address(tags: dict[str, Any]) -> str | None:
    parts = [
        _text(tags, key)
        for key in (
            "addr:postcode",
            "addr:province",
            "addr:city",
            "addr:ward",
            "addr:place",
            "addr:street",
            "addr:housenumber",
        )
    ]
    present = [part for part in parts if part]
    return ", ".join(present) if present else None


def _category(tags: dict[str, Any]) -> str:
    traditional_style = _traditional_inn_style(tags)
    if traditional_style:
        return traditional_style
    if tags.get("amenity") in {"public_bath", "spa"} or tags.get("natural") == "hot_spring":
        return "onsen"
    if tags.get("tourism") in {"hotel", "guest_house"} or tags.get("guest_house") == "ryokan":
        return "accommodation"
    if tags.get("tourism") in {"museum", "gallery"}:
        return "museum"
    if tags.get("amenity") == "place_of_worship":
        if tags.get("religion") == "shinto":
            return "shrine"
        if tags.get("religion") == "buddhist":
            return "temple"
        return "religious_site"
    if tags.get("leisure") == "park":
        return "garden"
    if tags.get("tourism") == "viewpoint":
        return "viewpoint"
    return "sight"


def _tags(tags: dict[str, Any]) -> list[str]:
    pairs: Iterable[tuple[str, Any]] = (
        ("onsen", tags.get("onsen")),
        ("tourism", tags.get("tourism")),
        ("amenity", tags.get("amenity")),
        ("historic", tags.get("historic")),
        ("leisure", tags.get("leisure")),
        ("guest-house", tags.get("guest_house")),
        ("lodging-style", _traditional_inn_style(tags)),
    )
    return [f"{label}:{value}" for label, value in pairs if isinstance(value, str) and value]


def _traditional_inn_style(tags: dict[str, Any]) -> str | None:
    names = " ".join(
        value
        for key in ("name", "name:ja")
        if (value := _text(tags, key))
    )
    if "宿坊" in names:
        return "temple lodging"
    if "民宿" in names:
        return "minshuku"
    return None
