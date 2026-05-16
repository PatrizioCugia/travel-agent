"""Google Places API (New) lookup.

Two public callables:

- `lookup_place()` — the simple "give me the top hit" used by `tp spike`.
- `lookup_with_scoring()` — M3 production lookup with multi-candidate
  scoring, a fallback query chain (kanji → romaji → relaxed), and a
  confidence threshold below which we return None and let the caller
  log it as a miss for manual review.

The legacy Places API is closed to new projects (2024); we use Places API
(New) exclusively. See M1-findings.md for the research backing this and
the cost/field-mask discussion.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import Any

import requests

log = logging.getLogger(__name__)

PLACES_NEW_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# Nagoya-area bias as the default. Per-place address keywords override this
# (see _bias_for_address) so non-Nagoya places — Tsumago, Hikone, Okuhida,
# KIX — don't get pulled into the wrong region by an overly tight bias.
NAGOYA_CENTER_LAT = 35.18
NAGOYA_CENTER_LNG = 136.91
NAGOYA_RADIUS_M = 25_000

# Keyword → (lat, lng) hints. Order matters for substring overlaps —
# more-specific keywords first.
_REGION_HINTS: list[tuple[str, tuple[float, float]]] = [
    ("kansai", (34.434, 135.244)),
    ("kix", (34.434, 135.244)),
    ("izumisano", (34.434, 135.244)),
    ("shin-hirayu", (36.180, 137.518)),
    ("hirayu", (36.180, 137.518)),
    ("okuhida", (36.180, 137.518)),
    ("shin-hotaka", (36.291, 137.581)),
    ("takayama", (36.140, 137.253)),
    ("tsumago", (35.587, 137.598)),
    ("nagiso", (35.587, 137.598)),
    ("magome", (35.529, 137.553)),
    ("nakatsugawa", (35.487, 137.500)),
    ("kiso", (35.587, 137.598)),
    ("hikone", (35.271, 136.260)),
    ("shiga", (35.005, 135.868)),
    ("seki", (35.494, 136.917)),
    ("tokoname", (34.881, 136.835)),
    ("atsuta", (35.127, 136.908)),
    ("nagoya", (NAGOYA_CENTER_LAT, NAGOYA_CENTER_LNG)),
    ("aichi", (NAGOYA_CENTER_LAT, NAGOYA_CENTER_LNG)),
]


def _bias_for_address(address: str | None) -> tuple[float, float]:
    if not address:
        return (NAGOYA_CENTER_LAT, NAGOYA_CENTER_LNG)
    lower = address.lower()
    for keyword, coords in _REGION_HINTS:
        if keyword in lower:
            return coords
    return (NAGOYA_CENTER_LAT, NAGOYA_CENTER_LNG)


# Field mask: Pro + Enterprise(rating/userRatingCount) only — both fit our
# free-tier budget for ~50 calls/trip. Avoid reviews/photos (Atmosphere).
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

# Confidence threshold below which we don't write to places.yaml.
CONFIDENCE_THRESHOLD = 0.60
# Gap between #1 and #2 below which we de-rate confidence (ambiguous).
AMBIGUITY_GAP = 0.10
# Distance gate: even if the API returns a high-confidence match for a query
# biased toward, say, Tsumago, reject it if the result is more than this many
# km from the bias center. Catches cases where a famous similarly-named place
# in another region outranks the actual local place on review count.
MAX_DISTANCE_FROM_BIAS_KM = 50.0


def _distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km. Good enough for region gating."""
    r_earth = 6371.0
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    return 2 * r_earth * math.asin(math.sqrt(a))


@dataclass
class LookupResult:
    """Production lookup output. Pure data, no API client coupling."""

    place_id: str
    lat: float
    lng: float
    name: str | None
    formatted_address: str | None
    types: list[str]
    rating: float | None
    user_ratings_total: int | None
    business_status: str | None
    confidence: float
    candidates_seen: int
    query_used: str
    language_used: str


def _normalize_tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _score_candidate(candidate: dict[str, Any], target_address: str | None) -> float:
    """Score 0.0 to 1.0.

    Weights chosen so a famous place (many reviews + operational) clears the
    0.60 confidence threshold even with zero address overlap — important
    because the API returns Japanese-script addresses when queried in `ja`
    and our `places.yaml` addresses are romaji, so token overlap is often
    zero by construction. Address remains useful as a tiebreaker.
    """
    score = 0.0

    # Reviews — primary signal that this is a real, known place.
    rc = candidate.get("userRatingCount") or 0
    if rc >= 1000:
        score += 0.50
    elif rc >= 100:
        score += 0.40
    elif rc >= 10:
        score += 0.25
    elif rc > 0:
        score += 0.10

    # Operational status — strong "still here" signal.
    business_status = candidate.get("businessStatus")
    if business_status == "OPERATIONAL":
        score += 0.20
    elif business_status is None:
        score += 0.05  # unknown — small benefit of the doubt
    # CLOSED_PERMANENTLY / CLOSED_TEMPORARILY → no bonus

    # Address overlap — bonus, primarily useful for disambiguating siblings.
    if target_address:
        target_tokens = _normalize_tokens(target_address)
        candidate_tokens = _normalize_tokens(candidate.get("formattedAddress", "") or "")
        if target_tokens:
            overlap = len(target_tokens & candidate_tokens) / len(target_tokens)
            score += 0.30 * overlap

    return min(score, 1.0)


def _request_text_search(
    query: str,
    language: str,
    api_key: str,
    *,
    bias_center: tuple[float, float] | None = None,
    page_size: int = 5,
) -> dict[str, Any]:
    if bias_center is None:
        bias_center = (NAGOYA_CENTER_LAT, NAGOYA_CENTER_LNG)
    body: dict[str, Any] = {
        "textQuery": query,
        "languageCode": language,
        "regionCode": "jp",
        "locationBias": {
            "circle": {
                "center": {
                    "latitude": bias_center[0],
                    "longitude": bias_center[1],
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
    return data


def lookup_place(
    name: str,
    address: str | None,
    api_key: str,
    *,
    language: str = "ja",
    page_size: int = 1,
) -> dict[str, Any] | None:
    """Simple single-result lookup used by `tp spike`. No scoring."""
    text_query = f"{name} {address}" if address else name
    data = _request_text_search(text_query, language, api_key, page_size=page_size)
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


def _build_attempts(
    name_en: str,
    name_local: str | None,
    address: str | None,
) -> list[tuple[str, str]]:
    """The fallback query chain from M1-findings.

    Order: kanji+address (ja) → romaji+address (ja) → kanji-only (ja) →
    romaji+"Nagoya" (en).
    """
    attempts: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(query: str, language: str) -> None:
        key = (query.strip(), language)
        if key[0] and key not in seen:
            attempts.append(key)
            seen.add(key)

    if name_local and address:
        add(f"{name_local} {address}", "ja")
    if address:
        add(f"{name_en} {address}", "ja")
    if name_local:
        add(name_local, "ja")
    add(f"{name_en} Nagoya", "en")
    return attempts


def lookup_with_scoring(
    name_en: str,
    name_local: str | None,
    address: str | None,
    api_key: str,
) -> LookupResult | None:
    """Multi-candidate lookup with scoring + fallback queries.

    Tries queries in priority order; for each, requests up to 5 candidates,
    scores them on (operational + address overlap + reviews), de-rates the
    top score if the runner-up is within AMBIGUITY_GAP, and returns the
    first attempt that yields confidence ≥ CONFIDENCE_THRESHOLD.

    Returns None if all attempts fail to meet the threshold — caller should
    log a miss for manual review (see `enrich.py`).
    """
    attempts = _build_attempts(name_en, name_local, address)
    bias = _bias_for_address(address)

    for query, language in attempts:
        data = _request_text_search(query, language, api_key, bias_center=bias, page_size=5)
        candidates = data.get("places") or []
        if not candidates:
            continue

        scored = sorted(
            ((c, _score_candidate(c, address)) for c in candidates),
            key=lambda x: x[1],
            reverse=True,
        )
        best, best_score = scored[0]

        if len(scored) > 1:
            second_score = scored[1][1]
            if (best_score - second_score) < AMBIGUITY_GAP:
                # Two candidates effectively tied — caller probably wants review
                best_score = best_score * 0.7

        if best_score < CONFIDENCE_THRESHOLD:
            continue

        loc = best.get("location") or {}
        display = best.get("displayName") or {}
        place_id = best.get("id")
        latitude = loc.get("latitude")
        longitude = loc.get("longitude")
        if not place_id or latitude is None or longitude is None:
            continue

        # Distance gate: reject matches far from the expected region.
        dist = _distance_km(float(latitude), float(longitude), bias[0], bias[1])
        if dist > MAX_DISTANCE_FROM_BIAS_KM:
            log.warning(
                "Best match for %r is %.0f km from bias center — wrong region",
                query,
                dist,
            )
            continue

        return LookupResult(
            place_id=place_id,
            lat=float(latitude),
            lng=float(longitude),
            name=display.get("text"),
            formatted_address=best.get("formattedAddress"),
            types=best.get("types") or [],
            rating=best.get("rating"),
            user_ratings_total=best.get("userRatingCount"),
            business_status=best.get("businessStatus"),
            confidence=round(best_score, 3),
            candidates_seen=len(candidates),
            query_used=query,
            language_used=language,
        )

    return None
