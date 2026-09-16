"""Shared, source-preserving shape for discovered places."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class DiscoveryCandidate:
    """One place returned by a discovery provider, before user selection."""

    source: str
    source_id: str
    source_url: str
    licence: str
    name: str
    category: str
    lat: float
    lng: float
    name_local: str | None = None
    address: str | None = None
    website: str | None = None
    opening_hours: str | None = None
    tags: list[str] = field(default_factory=list)
    distance_km: float | None = None

    @property
    def candidate_id(self) -> str:
        return f"{self.source}:{self.source_id}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DiscoveryCandidate:
        return cls(
            source=str(raw["source"]),
            source_id=str(raw["source_id"]),
            source_url=str(raw["source_url"]),
            licence=str(raw["licence"]),
            name=str(raw["name"]),
            category=str(raw["category"]),
            lat=float(raw["lat"]),
            lng=float(raw["lng"]),
            name_local=str(raw["name_local"]) if raw.get("name_local") else None,
            address=str(raw["address"]) if raw.get("address") else None,
            website=str(raw["website"]) if raw.get("website") else None,
            opening_hours=str(raw["opening_hours"]) if raw.get("opening_hours") else None,
            tags=[str(tag) for tag in raw.get("tags", [])],
            distance_km=float(raw["distance_km"]) if raw.get("distance_km") is not None else None,
        )
