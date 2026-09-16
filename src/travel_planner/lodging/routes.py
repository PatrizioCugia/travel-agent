"""Verified booking-route registry and safe routing guidance.

Availability channels are deliberately kept separate from the action a traveller
can take. A channel can report its own inventory without proving that an inn is
sold out everywhere; a booking page or contact route is never invoked by this
module. The registry is small, reviewed evidence rather than a scraped index.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal, cast

from travel_planner.maps.yaml_writer import round_trip_yaml
from travel_planner.paths import repo_root

Access = Literal["jalan_legacy_api", "public_booking_page", "booking_request", "contact"]
_ACCESS_VALUES: frozenset[str] = frozenset({
    "jalan_legacy_api", "public_booking_page", "booking_request", "contact",
})


@dataclass(frozen=True)
class BookingChannel:
    """One verified route to an inn, distinct from an availability verdict."""

    provider: str
    access: Access
    booking_url: str
    external_id: str | None = None
    contact: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class InnBookingRoutes:
    """Stable IDs and human-controlled routes for one Rakuten inn."""

    rakuten_hotel_no: int
    name: str
    verified_on: str
    channels: tuple[BookingChannel, ...]


class BookingRouteError(ValueError):
    """The local, reviewed route registry is malformed."""


def registry_path() -> Path:
    """The checked-in evidence registry, intentionally separate from trip state."""
    return repo_root() / "data" / "booking_routes.yaml"


def _text(record: Mapping[object, object], key: str, *, required: bool = True) -> str | None:
    value = record.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise BookingRouteError(f"{key!r} must be a non-empty string")
    return value.strip()


def _verified_on(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError as error:
            raise BookingRouteError("verified_on must be an ISO date") from error
    raise BookingRouteError("verified_on must be an ISO date")


def _channel(raw: object) -> BookingChannel:
    if not isinstance(raw, Mapping):
        raise BookingRouteError("each channel must be a mapping")
    provider = _text(raw, "provider")
    access = _text(raw, "access")
    booking_url = _text(raw, "booking_url")
    assert provider is not None
    assert access is not None
    assert booking_url is not None
    if access not in _ACCESS_VALUES:
        raise BookingRouteError(f"unsupported booking access {access!r}")
    return BookingChannel(
        provider=provider,
        access=cast(Access, access),
        booking_url=booking_url,
        external_id=_text(raw, "external_id", required=False),
        contact=_text(raw, "contact", required=False),
        notes=_text(raw, "notes", required=False),
    )


def load_registry(path: Path | None = None) -> dict[int, InnBookingRoutes]:
    """Load verified routes, rejecting ambiguous or malformed identities."""
    file = path or registry_path()
    if not file.exists():
        raise BookingRouteError(f"booking-route registry is missing: {file}")
    with file.open(encoding="utf-8") as handle:
        data = round_trip_yaml().load(handle)
    if not isinstance(data, Mapping):
        raise BookingRouteError("booking-route registry must be a mapping")
    raw_routes = data.get("routes")
    if not isinstance(raw_routes, list):
        raise BookingRouteError("booking-route registry requires a routes list")

    routes: dict[int, InnBookingRoutes] = {}
    for raw in raw_routes:
        if not isinstance(raw, Mapping):
            raise BookingRouteError("each route must be a mapping")
        hotel_no = raw.get("rakuten_hotel_no")
        if not isinstance(hotel_no, int) or hotel_no <= 0:
            raise BookingRouteError("rakuten_hotel_no must be a positive integer")
        if hotel_no in routes:
            raise BookingRouteError(f"duplicate Rakuten hotel number: {hotel_no}")
        raw_channels = raw.get("channels")
        if not isinstance(raw_channels, list):
            raise BookingRouteError("channels must be a list")
        name = _text(raw, "name")
        assert name is not None
        routes[hotel_no] = InnBookingRoutes(
            rakuten_hotel_no=hotel_no,
            name=name,
            verified_on=_verified_on(raw.get("verified_on")),
            channels=tuple(_channel(channel) for channel in raw_channels),
        )
    return routes


def get(hotel_no: int, path: Path | None = None) -> InnBookingRoutes | None:
    """Return a route record by canonical Rakuten hotel number."""
    return load_registry(path).get(hotel_no)


def _label(provider: str) -> str:
    labels = {
        "apa_partner": "APA Partner",
        "booking_com": "Booking.com",
        "koyasan_shukubo_association": "Koyasan Shukubo Association",
        "official_contact": "Official contact",
        "official_direct": "Official direct",
        "vacation_go": "VacationGo",
    }
    if provider in labels:
        return labels[provider]
    return provider.replace("_", " ").title()


def render(hotel_no: int, path: Path | None = None) -> str:
    """Render a compact, safe next-step sequence for an inn.

    This function does not fetch availability, submit a request, open a booking
    page, or send a message. It explains which source has what authority.
    """
    route = get(hotel_no, path)
    if route is None:
        return (
            f"No verified alternate route is recorded for Rakuten hotelNo {hotel_no}.\n"
            "Use check_availability first. If Rakuten is empty, use lodging_detail for the "
            "inn phone number and locate its official booking page before treating it as full."
        )

    lines = [
        f"{route.name} — booking route evidence verified {route.verified_on}",
        "1. Rakuten: run check_availability for the exact party and dates. A returned plan is "
        "bookable Rakuten-channel evidence; an empty result is unknown.",
        f"   https://travel.rakuten.co.jp/HOTEL/{route.rakuten_hotel_no}/"
        f"{route.rakuten_hotel_no}.html",
    ]
    if not route.channels:
        lines.append(
            "2. No alternate channel has been verified yet. Use the Rakuten plan link or "
            "lodging_detail."
        )
        return "\n".join(lines)

    lines.append("2. If Rakuten is empty, use the verified alternate route below:")
    for channel in route.channels:
        detail = _label(channel.provider)
        if channel.external_id:
            detail += f" #{channel.external_id}"
        if channel.access == "jalan_legacy_api":
            action = "Jalan stock API needs a pre-existing key; otherwise open its booking page."
        elif channel.access == "booking_request":
            action = "Submit a traveller-controlled request; a reply is the confirmation."
        elif channel.access == "contact":
            action = "Contact the inn directly; no availability claim is implied."
        else:
            action = "Open the public booking page and check the exact conditions there."
        lines.append(f"   - {detail}: {action}\n     {channel.booking_url}")
        if channel.contact:
            lines.append(f"     contact: {channel.contact}")
        if channel.notes:
            lines.append(f"     {channel.notes}")
    lines.append(
        "3. Do not submit a booking or enquiry from the planner. Record the source and "
        "timestamp after a human check."
    )
    return "\n".join(lines)


def audit(path: Path | None = None) -> str:
    """Summarize registry coverage; this checks routing evidence, not room stock."""
    routes = load_registry(path)
    channels = [channel for route in routes.values() for channel in route.channels]
    by_access = {
        access: sum(channel.access == access for channel in channels)
        for access in _ACCESS_VALUES
    }
    jalan = sum(channel.provider == "jalan" for channel in channels)
    without_alternative = sum(not route.channels for route in routes.values())
    return (
        f"{len(routes)} inns in the route registry; all have Rakuten identities. "
        f"{len(routes) - without_alternative} have a verified alternate route: "
        f"{jalan} Jalan identities, {by_access['public_booking_page']} public booking pages, "
        f"{by_access['booking_request']} request routes, and "
        f"{by_access['contact']} direct contacts. {without_alternative} currently rely on "
        "Rakuten alone. This is route coverage, not availability."
    )
