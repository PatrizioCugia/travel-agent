"""Restaurant search, via Google Places.

The honest framing, because it shapes what you should trust here: there is no
active public Tabelog API we can use. Do not scrape it. Hot Pepper Gourmet has
a public API but covers its own participating listings, so it can become a
separate coverage adapter rather than a substitute for careful restaurant
selection. This is Google-quality data, not Tabelog-quality, and every result
carries a Tabelog search link for a human to check the Japanese-side rating.

Nothing here scrapes Tabelog. It constructs a search URL a human opens.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import requests

from travel_planner.format import truncate
from travel_planner.geo import (
    PLACES_TEXT_SEARCH_URL,
    Location,
    api_key,
    distance_km,
    geocode,
)

# Pro tier + rating/priceLevel/hours. No photos or reviews (Atmosphere tier,
# expensive and useless in a terminal).
FOOD_FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.location",
    "places.rating",
    "places.userRatingCount",
    "places.priceLevel",
    "places.primaryTypeDisplayName",
    "places.types",
    "places.googleMapsUri",
    "places.websiteUri",
    "places.regularOpeningHours",
    "places.businessStatus",
])

TABELOG_SEARCH = "https://tabelog.com/en/rstLst/?sk={query}"

_EXPENSIVE = {"PRICE_LEVEL_EXPENSIVE", "PRICE_LEVEL_VERY_EXPENSIVE"}
# Types where walking in is the exception rather than the rule.
_BOOKING_TYPES = {"sushi_restaurant", "fine_dining_restaurant", "steak_house"}
_PRICE_GLYPH = {
    "PRICE_LEVEL_INEXPENSIVE": "¥",
    "PRICE_LEVEL_MODERATE": "¥¥",
    "PRICE_LEVEL_EXPENSIVE": "¥¥¥",
    "PRICE_LEVEL_VERY_EXPENSIVE": "¥¥¥¥",
}
_DAY_SHORT = {
    "Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed", "Thursday": "Thu",
    "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun",
}


@dataclass(frozen=True)
class FoodHit:
    place_id: str
    name: str
    address: str
    lat: float | None
    lng: float | None
    rating: float | None
    rating_count: int | None
    price_level: str | None
    kind: str | None
    types: list[str] = field(default_factory=list)
    maps_uri: str | None = None
    website: str | None = None
    weekday_hours: list[str] = field(default_factory=list)
    business_status: str | None = None
    distance_km: float | None = None

    @property
    def booking_likely(self) -> bool:
        """Heuristic — expensive, or a genre where counters are reserved.

        Never a fact. It exists so a place that needs booking six weeks out
        lands in the shortlist flagged, instead of being discovered too late.
        """
        if self.price_level in _EXPENSIVE:
            return True
        return bool(set(self.types) & _BOOKING_TYPES) and (self.rating or 0) >= 4.3

    @property
    def closed_days(self) -> list[str]:
        """Days the place is shut, parsed from Google's weekday descriptions."""
        out: list[str] = []
        for line in self.weekday_hours:
            match = re.match(r"^(\w+day):\s*Closed", line.strip())
            if match:
                out.append(_DAY_SHORT.get(match.group(1), match.group(1)[:3]))
        return out

    def tabelog_url(self) -> str:
        return TABELOG_SEARCH.format(query=quote(self.name))

    def line(self) -> str:
        price = _PRICE_GLYPH.get(self.price_level or "", "")
        rating = f"{self.rating} ({self.rating_count})" if self.rating_count else "unrated"
        flags = []
        if self.booking_likely:
            flags.append("likely needs booking")
        if self.closed_days:
            flags.append(f"closed {'/'.join(self.closed_days)}")
        if self.business_status and self.business_status != "OPERATIONAL":
            flags.append(self.business_status.lower().replace("_", " "))
        dist = f" · {self.distance_km * 1000:.0f} m" if self.distance_km is not None else ""

        head = f"{self.name}"
        if price:
            head += f"  {price}"
        second = f"    {rating} · {self.kind or 'restaurant'}{dist}"
        if flags:
            second += f" · {', '.join(flags)}"
        third = f"    {truncate(self.address, 70)}"
        # The place id has to be here: it is the handle every downstream tool
        # takes (shortlist_add_restaurant), and without it a result cannot be
        # acted on without a second search.
        fourth = f"    {self.place_id}  ·  tabelog: {self.tabelog_url()}"
        return "\n".join([head, second, third, fourth])


def search_food(
    near: str,
    *,
    dish: str | None = None,
    radius_m: int = 1200,
    min_rating: float | None = None,
    open_now: bool = False,
    limit: int = 12,
    key: str | None = None,
    language: str = "en",
) -> tuple[Location, list[FoodHit]]:
    """Find places to eat near a phrase, optionally by dish.

    `near` is anything Places understands: a station, a shrine, a town, or a
    place already in your trip ('Todai-ji Nara').
    """
    centre = geocode(near, key)
    query = f"{dish} restaurant" if dish else "restaurant"

    body: dict[str, Any] = {
        "textQuery": query,
        "regionCode": "jp",
        "languageCode": language,
        "pageSize": min(max(limit, 1), 20),
        "locationBias": {
            "circle": {
                "center": {"latitude": centre.lat, "longitude": centre.lng},
                "radius": float(radius_m),
            }
        },
        "includedType": "restaurant",
    }
    if min_rating is not None:
        body["minRating"] = min_rating
    if open_now:
        body["openNow"] = True

    resp = requests.post(
        PLACES_TEXT_SEARCH_URL,
        json=body,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key(key),
            "X-Goog-FieldMask": FOOD_FIELD_MASK,
        },
        timeout=15,
    )
    resp.raise_for_status()
    raw = resp.json().get("places") or []

    hits = [_parse_hit(p, centre) for p in raw]
    # locationBias is a hint, not a boundary: a search near Tōdai-ji happily
    # returns a well-reviewed place 30 km away in Osaka. searchText only
    # supports rectangular locationRestriction, so gate on distance here.
    # Twice the requested radius, because the bias is fuzzy and a good place
    # one street outside the circle is still a good place.
    gate_km = (radius_m * 2) / 1000
    within = [h for h in hits if h.distance_km is None or h.distance_km <= gate_km]
    within.sort(key=lambda h: h.distance_km if h.distance_km is not None else 1e9)
    return centre, within[:limit]


def local_name(place_id: str, key: str | None = None) -> str | None:
    """The Japanese display name, for a shortlist entry's name_local.

    A second call, because Places returns one language per request. Only worth
    making when a candidate is being kept, not for every search result.
    """
    resp = requests.get(
        f"https://places.googleapis.com/v1/places/{place_id}",
        params={"languageCode": "ja", "regionCode": "jp"},
        headers={"X-Goog-Api-Key": api_key(key), "X-Goog-FieldMask": "displayName"},
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    name: str | None = (resp.json().get("displayName") or {}).get("text")
    return name


def render(centre: Location, hits: list[FoodHit], *, dish: str | None = None) -> str:
    what = dish or "places to eat"
    header = f"{what} near {centre.name}"
    if not hits:
        return (
            f"{header}\n\nNothing came back. Google's coverage of small Japanese "
            "restaurants is patchy — a place with no listing is not a place that "
            "does not exist. Try the Japanese name of the dish, or a wider radius."
        )
    lines = [header, ""]
    lines.extend(h.line() for h in hits)
    lines.append("")
    lines.append(
        f"{len(hits)} result(s). Google data — check the Tabelog link before trusting a "
        "rating, and 'likely needs booking' is a guess from price and genre, not a fact."
    )
    return "\n".join(lines)


def _parse_hit(p: dict[str, Any], centre: Location) -> FoodHit:
    loc = p.get("location") or {}
    lat, lng = loc.get("latitude"), loc.get("longitude")
    return FoodHit(
        place_id=str(p.get("id", "")),
        name=(p.get("displayName") or {}).get("text") or "(unnamed)",
        address=p.get("formattedAddress") or "",
        lat=lat,
        lng=lng,
        rating=p.get("rating"),
        rating_count=p.get("userRatingCount"),
        price_level=p.get("priceLevel"),
        kind=(p.get("primaryTypeDisplayName") or {}).get("text"),
        types=p.get("types") or [],
        maps_uri=p.get("googleMapsUri"),
        website=p.get("websiteUri"),
        weekday_hours=(p.get("regularOpeningHours") or {}).get("weekdayDescriptions") or [],
        business_status=p.get("businessStatus"),
        distance_km=distance_km(centre.lat, centre.lng, lat, lng),
    )


def fetch_place(place_id: str, key: str | None = None, *, language: str = "en") -> FoodHit | None:
    """One place by id, for turning a search result into a shortlist entry."""
    resp = requests.get(
        f"https://places.googleapis.com/v1/places/{place_id}",
        params={"languageCode": language, "regionCode": "jp"},
        headers={
            "X-Goog-Api-Key": api_key(key),
            "X-Goog-FieldMask": FOOD_FIELD_MASK.replace("places.", ""),
        },
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    p = resp.json()
    loc = p.get("location") or {}
    return FoodHit(
        place_id=place_id,
        name=(p.get("displayName") or {}).get("text") or "(unnamed)",
        address=p.get("formattedAddress") or "",
        lat=loc.get("latitude"),
        lng=loc.get("longitude"),
        rating=p.get("rating"),
        rating_count=p.get("userRatingCount"),
        price_level=p.get("priceLevel"),
        kind=(p.get("primaryTypeDisplayName") or {}).get("text"),
        types=p.get("types") or [],
        maps_uri=p.get("googleMapsUri"),
        website=p.get("websiteUri"),
        weekday_hours=(p.get("regularOpeningHours") or {}).get("weekdayDescriptions") or [],
        business_status=p.get("businessStatus"),
        distance_km=None,
    )
