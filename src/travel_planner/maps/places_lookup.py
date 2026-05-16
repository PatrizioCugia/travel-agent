"""Google Places API (New) lookup.

Phase 1: single-result Text Search with a Nagoya-biased query. M3 will add
candidate scoring, fallback queries, and low-confidence flagging — for now we
just need a working spine call.

The legacy Places API is closed to new projects (2024); this module uses
Places API (New). See M1-findings.md for the research backing this choice.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

log = logging.getLogger(__name__)

PLACES_NEW_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# Nagoya-area bias for travel-planner's first trip. Phase-1 hardcode; we'll
# generalize when a second trip enters the system.
NAGOYA_CENTER_LAT = 35.18
NAGOYA_CENTER_LNG = 136.91
NAGOYA_RADIUS_M = 25_000

# Field mask: keeps us in the Pro tier (free for our ~50 calls/trip). Rating
# and userRatingCount push to Enterprise but stay within its 1000 free
# events/month. Avoid reviews/photos — those are Atmosphere SKU.
DEFAULT_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.types",
        "places.rating",
        "places.userRatingCount",
        "places.businessStatus",
    ]
)


def lookup_place(
    name: str,
    address: str | None,
    api_key: str,
    *,
    language: str = "ja",
    page_size: int = 1,
) -> dict[str, Any] | None:
    """Look up a place via Places API (New) Text Search.

    Returns a normalized dict (place_id, name, formatted_address, lat, lng,
    types, rating, user_ratings_total, business_status) or None on zero
    results.

    Phase 1 returns the top result with no candidate scoring. M3 will add
    multi-candidate scoring (token overlap + business_status + rating
    tiebreak), fallback queries (kanji → romaji → drop address), and a
    confidence threshold below which we write to `lookup-misses.md` instead
    of `places.yaml`.
    """
    text_query = f"{name} {address}" if address else name
    body: dict[str, Any] = {
        "textQuery": text_query,
        "languageCode": language,
        "regionCode": "jp",
        "locationBias": {
            "circle": {
                "center": {
                    "latitude": NAGOYA_CENTER_LAT,
                    "longitude": NAGOYA_CENTER_LNG,
                },
                "radius": float(NAGOYA_RADIUS_M),
            }
        },
        "pageSize": page_size,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": DEFAULT_FIELD_MASK,
    }
    resp = requests.post(
        PLACES_NEW_TEXT_SEARCH_URL,
        json=body,
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()

    places = data.get("places") or []
    if not places:
        log.warning("No results for query: %s", text_query)
        return None

    top = places[0]
    loc = top.get("location") or {}
    display = top.get("displayName") or {}
    return {
        "place_id": top.get("id"),
        "name": display.get("text"),
        "formatted_address": top.get("formattedAddress"),
        "lat": loc.get("latitude"),
        "lng": loc.get("longitude"),
        "types": top.get("types") or [],
        "rating": top.get("rating"),
        "user_ratings_total": top.get("userRatingCount"),
        "business_status": top.get("businessStatus"),
    }
