"""Geocoding and distance, shared by lodging and food search.

Google Places already knows every place name in Japan and is already wired up
from phase 1, so it is the front door for any "near X" phrasing before we hand
coordinates to an API that only speaks in numbers.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

import requests

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# Location only. Deliberately narrower than the phase-1 lookup mask: we are
# geocoding a town, not identifying a business.
GEOCODE_FIELD_MASK = "places.id,places.displayName,places.formattedAddress,places.location"


class GeocodeError(RuntimeError):
    """The place phrase could not be turned into coordinates."""


@dataclass(frozen=True)
class Location:
    name: str
    address: str
    lat: float
    lng: float
    place_id: str


def api_key(explicit: str | None = None) -> str:
    key = explicit or os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not key:
        raise GeocodeError(
            "GOOGLE_MAPS_API_KEY is not set. Add it to .env — the same key phase 1 uses."
        )
    return key


def geocode(where: str, key: str | None = None, *, language: str = "en") -> Location:
    """Turn 'Kinosaki Onsen' or '城崎温泉' into coordinates."""
    resp = requests.post(
        PLACES_TEXT_SEARCH_URL,
        json={"textQuery": where, "regionCode": "jp", "languageCode": language, "pageSize": 1},
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key(key),
            "X-Goog-FieldMask": GEOCODE_FIELD_MASK,
        },
        timeout=10,
    )
    resp.raise_for_status()
    places = resp.json().get("places") or []
    if not places:
        raise GeocodeError(
            f"Google Places found nothing for {where!r}. Try the Japanese name, "
            "or a nearby station."
        )
    top = places[0]
    loc = top.get("location") or {}
    return Location(
        name=(top.get("displayName") or {}).get("text") or where,
        address=top.get("formattedAddress") or "",
        lat=float(loc["latitude"]),
        lng=float(loc["longitude"]),
        place_id=str(top.get("id", "")),
    )


def distance_km(lat1: float, lng1: float, lat2: float | None, lng2: float | None) -> float | None:
    """Great-circle distance. Good enough for 'how far from the station'."""
    if lat2 is None or lng2 is None:
        return None
    r = 6371.0
    dlat, dlng = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))
