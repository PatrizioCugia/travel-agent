"""Lodging search: resolve a place name to coordinates, then ask Rakuten.

Rakuten has no notion of "near Kinosaki Onsen" — it wants coordinates or its
own area-code tree. Google Places already knows every place name in Japan and
is already wired up for phase 1, so the search path is: geocode the phrase,
then query Rakuten by lat/lng, remembering that searchRadius is capped at
3.0 km (not 30).

Results lead with the Japanese name because that is all Rakuten has. English
names arrive later, when a candidate is promoted to the shortlist and gets a
Places lookup of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from travel_planner.format import meals, name_line, review, truncate, yen_kr
from travel_planner.geo import Location, distance_km, geocode
from travel_planner.lodging.rakuten import Hotel, RakutenTravel, SqueezeCondition

# Bath keywords, scanned in the hotel name and Rakuten's hotelSpecial blurb.
# A heuristic, and labelled as one — Rakuten exposes no structured bath field
# on search results, only on HotelDetailSearch with responseType=large.
_BATH_HINTS: list[tuple[str, str]] = [
    ("露天", "open-air bath"),
    ("貸切", "private bath"),
    ("家族風呂", "private bath"),
    ("大浴場", "large bath"),
    ("温泉", "onsen"),
    ("源泉", "onsen"),
]


@dataclass(frozen=True)
class LodgingHit:
    hotel: Hotel
    distance_km: float | None

    def line(self, nights: int = 1) -> str:
        h = self.hotel
        best = h.cheapest
        price = yen_kr(best.total) if best else "price n/a"
        meal = meals(best.with_dinner, best.with_breakfast) if best else ""
        caveat = "  (first night)" if nights > 1 and best and best.total else ""
        baths = ", ".join(bath_hints(h))
        where = h.nearest_station or "?"
        dist = f" · {self.distance_km:.1f} km from centre" if self.distance_km is not None else ""
        head = f"{h.hotel_no}  {price} {meal}{caveat}  {name_line(None, h.name)}"
        second = f"       {review(h.review_average, h.review_count)}"
        if baths:
            second += f" · {baths}"
        second += f" · {truncate(where, 40)}{dist}"
        third = f"       {h.page_url}"
        return "\n".join([head, second, third])


def bath_hints(hotel: Hotel) -> list[str]:
    """Best-effort bath/onsen labels from the name and Rakuten's blurb.

    Heuristic by necessity: search responses carry no structured bath field.
    `tp lodging show` fetches the real facility detail when it matters.
    """
    haystack = f"{hotel.name} {hotel.special or ''}"
    found: list[str] = []
    for needle, label in _BATH_HINTS:
        if needle in haystack and label not in found:
            found.append(label)
    return found


def search_near(
    client: RakutenTravel,
    where: str,
    checkin: date,
    checkout: date,
    *,
    radius_km: float = 3.0,
    adults: int = 2,
    rooms: int = 1,
    max_charge: int | None = None,
    onsen: bool = False,
    with_dinner: bool = False,
    limit: int = 20,
) -> tuple[Location, list[LodgingHit]]:
    """Geocode `where`, then return bookable lodging around it, cheapest first."""
    centre = geocode(where)
    radius_km = min(max(radius_km, 0.1), 3.0)   # API cap, enforced here not there
    squeeze: list[SqueezeCondition] = []
    if onsen:
        squeeze.append("onsen")
    if with_dinner:
        squeeze.append("dinner")

    hotels = client.vacancy(
        checkin,
        checkout,
        lat=centre.lat,
        lng=centre.lng,
        radius_km=radius_km,
        adults=adults,
        rooms=rooms,
        max_charge=max_charge,
        squeeze=squeeze or None,
        sort="+roomCharge",
    )
    hits = [
        LodgingHit(hotel=h, distance_km=distance_km(centre.lat, centre.lng, h.lat, h.lng))
        for h in hotels
    ]
    return centre, hits[:limit]


def render(
    centre: Location,
    hits: list[LodgingHit],
    checkin: date,
    checkout: date,
    *,
    radius_km: float,
) -> str:
    nights = (checkout - checkin).days
    header = (
        f"{centre.name} — {checkin} → {checkout}, {nights} night(s), "
        f"within {radius_km:g} km"
    )
    if not hits:
        return (
            f"{header}\n\n"
            "Nothing bookable through Rakuten. Its empty answer can mean sold out, a "
            "calendar that has not opened yet, or no plan inventory supplied to Rakuten, "
            "so this is not proof the inns are full. Check the inn's official booking "
            "path before deciding whether a Rakuten watch is useful."
        )
    lines = [header, ""]
    lines.extend(hit.line(nights) for hit in hits)
    lines.append("")
    lines.append(f"{len(hits)} result(s). Prices are for the whole party, first night.")
    return "\n".join(lines)


def detail_text(hotel: Hotel) -> str:
    """Facility detail for `tp lodging show` / the lodging_detail MCP tool."""
    d: dict[str, Any] = hotel.detail_info or {}
    f: dict[str, Any] = hotel.facilities_info or {}
    out = [f"{hotel.hotel_no}  {hotel.name}", f"  {hotel.address}"]
    if hotel.nearest_station:
        out.append(f"  nearest station: {hotel.nearest_station}")
    if hotel.telephone:
        out.append(f"  tel: {hotel.telephone}")
    out.append(f"  reviews: {review(hotel.review_average, hotel.review_count)}")
    checkin_t, checkout_t = d.get("checkinTime"), d.get("checkoutTime")
    if checkin_t or checkout_t:
        out.append(f"  check-in {checkin_t or '?'} / check-out {checkout_t or '?'}")
    baths = bath_hints(hotel)
    if baths:
        out.append(f"  bath: {', '.join(baths)}")
    for label, key in (("rooms", "hotelRoomNum"), ("facilities", "hotelFacilities")):
        if f.get(key):
            out.append(f"  {label}: {truncate(str(f[key]), 200)}")
    if hotel.special:
        out.append(f"  {truncate(hotel.special, 240)}")
    out.append(f"  {hotel.page_url}")
    return "\n".join(out)
