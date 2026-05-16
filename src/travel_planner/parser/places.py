"""places.yaml parsing + validation.

Loads a trip's places.yaml into a list of validated PlaceModel instances.

This module only READS the YAML. The format-preserving round-trip (writing
lat/lng/google_place_id back into places.yaml after lookup) lives in
maps/places_lookup.py and is M3's concern — keep them separate.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator
from ruamel.yaml import YAML

from travel_planner.schema import PLACE_CATEGORIES

_yaml_reader = YAML(typ="safe")

# kebab-case slug: lowercase ASCII, alphanumeric segments joined by single
# hyphens. Leading digits allowed (e.g. `25-ji-made-ice` from the Nagoya v0
# doc).
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class PlaceModel(BaseModel):
    """A single entry in places.yaml. Mirrors travel_planner.schema.Place."""

    id: str
    name_en: str
    category: str
    name_local: str | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    google_place_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    urls: dict[str, str] = Field(default_factory=dict)
    notes: str | None = None

    @field_validator("id")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(
                f"id={v!r} must be lowercase kebab-case "
                "(start with a-z, then a-z/0-9/- with no leading/trailing/double hyphens)"
            )
        return v

    @field_validator("category")
    @classmethod
    def _validate_category(cls, v: str) -> str:
        if v not in PLACE_CATEGORIES:
            raise ValueError(f"category={v!r} not in allowed set {sorted(PLACE_CATEGORIES)}")
        return v


def load_places(places_yaml: Path) -> list[PlaceModel]:
    """Load and validate places.yaml. Returns a list of PlaceModel.

    Empty file → empty list. Raises FileNotFoundError if the file is missing,
    ValueError if the top-level YAML isn't a list, and pydantic.ValidationError
    if any entry fails validation.
    """
    if not places_yaml.exists():
        raise FileNotFoundError(f"places.yaml not found at {places_yaml}")
    with places_yaml.open("r", encoding="utf-8") as f:
        raw: Any = _yaml_reader.load(f)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"places.yaml must be a YAML list at top level, got {type(raw).__name__}")
    return [PlaceModel.model_validate(item) for item in raw]
