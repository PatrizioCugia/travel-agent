"""MCP server exposing the travel planner to Claude Code.

The point of this file: rather than teaching Claude to shell out to `tp` and
parse stdout, expose the planner as tools it can compose — resolve an inn,
check the dates, keep the good one, watch the ones that aren't open yet — in
one turn, in the repo, with the markdown still canonical.

Every tool returns compact text, never raw JSON. Rakuten payloads are enormous
and would eat the context window for no benefit: the model needs the handful
of fields it will actually reason about, plus a URL for the rest.

Registered in .mcp.json at the repo root, so it is project-scoped.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any, Literal, cast

import httpx
import requests
from dotenv import load_dotenv
from mcp.server import MCPServer

from travel_planner import shortlist
from travel_planner import trips as trip_service
from travel_planner.discovery import DiscoveryCache, bathing_directory
from travel_planner.discovery import bathing as bathing_discovery
from travel_planner.discovery import osm as osm_discovery
from travel_planner.food import search as food_search
from travel_planner.format import meals_en, yen, yen_kr
from travel_planner.geo import GeocodeError, distance_km, geocode
from travel_planner.itinerary import render_day_feasibility
from travel_planner.lodging import observations, routes, watch
from travel_planner.lodging.rakuten import Plan, RakutenError, RakutenTravel
from travel_planner.lodging.search import bath_hints, detail_text, render, search_near
from travel_planner.logging_setup import quiet_http_logging
from travel_planner.paths import discovery_cache_path, repo_root

load_dotenv(repo_root() / ".env")
quiet_http_logging()   # Rakuten keys ride in the query string; see logging_setup

mcp: MCPServer[Any] = MCPServer(
    "tp",
    instructions=(
        "Personal Japan trip planning. Markdown in trips/ is canonical; SQLite and "
        "map artifacts are regenerated views. Find candidates first, keep them in "
        "shortlist.yaml, and promote only after the traveller chooses. Nothing here "
        "books, emails, or changes an external service. Rakuten returns the same empty "
        "answer for sold out, a calendar not open yet, and absent provider inventory; "
        "never present an empty result as proof a place is full."
    ),
)

_client: RakutenTravel | None = None


def _rakuten() -> RakutenTravel:
    global _client
    if _client is None:
        _client = RakutenTravel()   # shared, so the 1 QPS floor is respected
    return _client


def _obs() -> sqlite3.Connection:
    return observations.connect()


def _candidate_cache() -> DiscoveryCache:
    return DiscoveryCache(discovery_cache_path())


# Failures a tool explains in its answer instead of raising: bad input, a
# missing key, a provider rejecting the call, or the network. Anything else is
# a bug and should still surface as one.
_EXPECTED_FAILURES = (
    ValueError,
    RakutenError,
    GeocodeError,
    httpx.HTTPError,
    requests.RequestException,
)


def _failed(action: str, error: Exception) -> str:
    return f"{action} failed: {error}"


def _stay(checkin: str, checkout: str) -> tuple[date, date]:
    """Parse a YYYY-MM-DD stay, rejecting a reversed one before Rakuten sees it."""
    try:
        ci, co = date.fromisoformat(checkin), date.fromisoformat(checkout)
    except ValueError as error:
        raise ValueError(f"dates must be YYYY-MM-DD ({error})") from error
    if co <= ci:
        raise ValueError(f"checkout {checkout} must be after checkin {checkin}")
    return ci, co


def _unit_price(plan: Plan) -> str:
    """Rakuten's per-person or per-room price, when chargeFlag names the unit."""
    if plan.unit_charge is None:
        return ""
    if plan.charge_flag == 0:
        return f" · {yen(plan.unit_charge)} per person"
    if plan.charge_flag == 1:
        return f" · {yen(plan.unit_charge)} per room"
    return ""


# --------------------------------------------------------------- trip state

@mcp.tool()
def trip_overview(trip: str) -> str:
    """Read a trip's canonical Markdown and summarize its current planning state.

    This reads trip.md, places.yaml, and day files. It does not use a potentially
    stale SQLite index and does not change any file.
    """
    report = trip_service.validate_trip(trip)
    if not report.ok or report.trip is None:
        return "Trip is not valid:\n" + "\n".join(f"- {error}" for error in report.errors)
    dates = "dates not set"
    if report.trip.start_date or report.trip.end_date:
        dates = f"{report.trip.start_date or '?'} → {report.trip.end_date or '?'}"
    themes = ", ".join(report.trip.themes) or "none"
    try:
        pending = f"{len(shortlist.load(report.slug))} shortlist candidate(s)"
    except ValueError as error:
        pending = f"shortlist unreadable: {error}"
    return (
        f"{report.trip.name} ({report.slug})\n"
        f"  {dates} · themes: {themes}\n"
        f"  {len(report.places)} committed place(s), {len(report.days)} day file(s), "
        f"{report.day_place_count} planned stop(s), {pending}"
    )


@mcp.tool()
def validate_trip(trip: str) -> str:
    """Validate trip Markdown and place references without writing any state."""
    report = trip_service.validate_trip(trip)
    if not report.ok:
        return "Trip is not valid:\n" + "\n".join(f"- {error}" for error in report.errors)
    return (
        f"Valid {report.slug}: {len(report.places)} place(s), {len(report.days)} day(s), "
        f"{report.day_place_count} day-place reference(s)."
    )


@mcp.tool()
def sync_trip(trip: str, lookup_missing_places: bool = True, force_lookup: bool = False) -> str:
    """Rebuild a trip's SQLite index from canonical Markdown.

    Missing coordinates and Google Place IDs are looked up only when
    `lookup_missing_places` is true. The cached lookup makes ordinary re-syncs
    cheap. Run this after promoting a shortlisted candidate before generating a map.
    """
    try:
        report = trip_service.sync_trip(
            trip,
            lookup=lookup_missing_places,
            force_lookup=force_lookup,
        )
    except trip_service.TripError as error:
        return f"Cannot sync trip: {error}"
    enrichment = report.enrichment
    detail = ""
    if enrichment is not None and enrichment.needed_lookup:
        detail = (
            f" Lookup: {enrichment.new_matches} matched, {enrichment.cache_hits} cached, "
            f"{len(enrichment.misses)} miss(es)."
        )
    elif report.lookup_skipped_reason:
        detail = f" Lookup: {report.lookup_skipped_reason}."
    return (
        f"Synced {report.validation.slug}: {len(report.validation.places)} place(s), "
        f"{len(report.validation.days)} day(s). {report.missing_place_ids} place(s) still "
        f"need a Google Place ID or coordinates.{detail}"
    )


@mcp.tool()
def generate_trip_map(trip: str) -> str:
    """Generate CSV, KML, route links, and indexes from a previously synced trip."""
    try:
        report = trip_service.generate_trip_map(trip)
        slug = trip_service.resolve_trip_slug(trip)
    except (trip_service.TripError, ValueError) as error:
        return f"Cannot generate map: {error}"
    relative_files = [str(path.relative_to(repo_root())) for path in report.files_written]
    return (
        f"Generated {len(relative_files)} artifact(s) for {slug}: "
        f"{report.places_pinned}/{report.places_total} pinned, "
        f"{report.days_with_routes} day route(s).\n"
        + "\n".join(f"- {path}" for path in relative_files)
    )


@mcp.tool()
def check_day_feasibility(trip: str, day: int, travel_mode: str = "transit") -> str:
    """Check the current order of one day and return a Google Maps link per leg.

    This uses only straight-line distance to flag implausible gaps. It does not
    claim live public-transit timings, fares, road conditions, or opening hours.
    It reads the day as currently written in Markdown; coordinates come from
    places.yaml, where sync_trip records any it looks up.
    """
    if travel_mode not in {"walking", "transit", "driving"}:
        return "travel_mode must be one of: walking, transit, driving"
    try:
        slug = trip_service.resolve_trip_slug(trip)
        selected_day = trip_service.day_view(slug, day)
    except trip_service.TripError as error:
        return f"Cannot assess day: {error}"
    if selected_day is None:
        return f"Day {day} has no day file in trips/{slug}/days."
    mode = cast(Literal["walking", "transit", "driving"], travel_mode)
    return render_day_feasibility(selected_day, mode)


# --------------------------------------------------------------- discovery

@mcp.tool()
def discover_nearby(
    near: str,
    kind: str,
    radius_m: int = 4_000,
    limit: int = 12,
) -> str:
    """Find nearby onsens, lodging, traditional inns, or sights.

    `kind` must be `onsen`, `ryokan`, `traditional_inn`, or `sight`.
    `traditional_inn` is an explicitly named 民宿 (minshuku) or 宿坊 (temple
    lodging), rather than a generic hotel or ryokan. For an exact Japanese
    onsen-area or bath name in the reviewed local directory, return its official
    Japanese source before falling back to OpenStreetMap. OSM results are cached
    locally so a chosen candidate can be added to a trip shortlist by its
    candidate ID. Neither source proves current opening or bookability.
    """
    if kind not in {"onsen", "ryokan", "traditional_inn", "sight"}:
        return "kind must be one of: onsen, ryokan, traditional_inn, sight"
    if kind == "onsen":
        official_directory = bathing_directory.render(near)
        if official_directory is not None:
            return official_directory
    try:
        centre = geocode(near)
        candidates = osm_discovery.search_nearby(
            kind,  # type: ignore[arg-type]  # checked against the literal set above
            lat=centre.lat,
            lng=centre.lng,
            radius_m=radius_m,
            limit=limit,
        )
    except Exception as error:
        return f"Discovery failed: {type(error).__name__}: {error}"
    _candidate_cache().put_many(candidates)
    header = f"{kind} near {centre.name} — OpenStreetMap, within {radius_m:,} m"
    if not candidates:
        return (
            f"{header}\n\nNo named candidates returned. "
            "Try a larger radius or a Japanese place name."
        )
    lines = [header, ""]
    for candidate in candidates:
        distance = (
            f" · {candidate.distance_km * 1000:.0f} m"
            if candidate.distance_km is not None
            else ""
        )
        local = f" / {candidate.name_local}" if candidate.name_local else ""
        lines.append(f"{candidate.candidate_id}  {candidate.name}{local}")
        detail = f"  {candidate.category}{distance}"
        if candidate.opening_hours:
            detail += f" · hours: {candidate.opening_hours}"
        if candidate.tags:
            detail += f" · {', '.join(candidate.tags)}"
        lines.append(detail)
        lines.append(f"  {candidate.source_url}")
    lines.extend(["", "Data © OpenStreetMap contributors (ODbL)."])
    return "\n".join(lines)


@mcp.tool()
def bathing_access(name: str) -> str:
    """Show reviewed tattoo, day-use, and private-bath access evidence for a bath.

    Use after discover_nearby returns an onsen, sento, sauna, or onsen area.
    This only reports source-linked local records. No match means unknown, not
    tattoo refusal. The tool never infers a policy from OSM, reviews, or a
    neighbouring bath; check the operator before a visit where entry matters.
    """
    return bathing_discovery.render(name)


@mcp.tool()
def bathing_access_audit() -> str:
    """Summarize reviewed tattoo/access evidence in the local bathing registry."""
    return bathing_discovery.audit()


@mcp.tool()
def shortlist_add_activity(
    trip: str,
    candidate_id: str,
    tags: list[str] | None = None,
    notes: str | None = None,
) -> str:
    """Keep one candidate returned by discover_nearby in a trip's shortlist."""
    candidate = _candidate_cache().get(candidate_id)
    if candidate is None:
        return (
            f"{candidate_id!r} is not in the local discovery cache. Run discover_nearby again, "
            "then pass its exact candidate ID."
        )
    entry = shortlist.activity_entry(
        source=candidate.source,
        source_id=candidate.source_id,
        name=candidate.name,
        name_local=candidate.name_local,
        category=candidate.category,
        address=candidate.address,
        lat=candidate.lat,
        lng=candidate.lng,
        source_url=candidate.source_url,
        website=candidate.website,
        tags=[*candidate.tags, *(tags or [])],
        notes=notes,
        query=f"discover_nearby {candidate.source}:{candidate.source_id}",
    )
    try:
        entry_id, added = shortlist.add(trip, entry)
    except ValueError as error:
        return f"Cannot update shortlist: {error}"
    if not added:
        return f"{entry_id} is already on {trip}'s shortlist."
    return f"Added {entry_id} to {trip}'s shortlist — {candidate.name}."

@mcp.tool()
def find_lodging(
    where: str,
    checkin: str,
    checkout: str,
    adults: int = 2,
    rooms: int = 1,
    radius_km: float = 3.0,
    max_yen: int | None = None,
    onsen: bool = False,
    with_dinner: bool = False,
    limit: int = 20,
) -> str:
    """Find bookable lodging near a place, for given dates.

    `where` is any phrase Google Places understands: a town, a station, an
    onsen village, a temple ('Kinosaki Onsen', 'Todai-ji Nara'). Dates are
    YYYY-MM-DD. radius_km is capped at 3.0 by the Rakuten API. Set onsen for
    hot-spring inns and with_dinner for half-board plans. Prices are the whole
    party's total (every adult, every room) for the first night only, and
    max_yen caps that same total.
    """
    try:
        ci, co = _stay(checkin, checkout)
        centre, hits = search_near(
            _rakuten(), where, ci, co,
            radius_km=radius_km, adults=adults, rooms=rooms,
            max_charge=max_yen, onsen=onsen, with_dinner=with_dinner, limit=limit,
        )
    except _EXPECTED_FAILURES as error:
        return _failed("Lodging search", error)
    return render(centre, hits, ci, co, radius_km=min(max(radius_km, 0.1), 3.0))


@mcp.tool()
def resolve_inn(name: str) -> str:
    """Find a lodging's Rakuten hotelNo by name, so it can be checked or watched.

    Use the Japanese name when you have it — '湯原温泉 湯本荘' resolves far more
    reliably than romaji. A place with no result may simply not sell through
    Rakuten; many small minshuku take phone and email bookings only.
    """
    try:
        hits = _rakuten().resolve(name)
    except _EXPECTED_FAILURES as error:
        return _failed("Inn lookup", error)
    if not hits:
        return (
            f"No Rakuten listing for {name!r}. Try the Japanese name, or accept that "
            "the inn does not sell through Rakuten — plenty of good ones don't, and "
            "take bookings by phone or email instead."
        )
    lines = []
    for h in hits[:8]:
        coords = f"{h.lat:.5f},{h.lng:.5f}" if h.lat and h.lng else "no coords"
        reviews = f"{h.review_average}★ ({h.review_count})" if h.review_count else "no reviews"
        baths = ", ".join(bath_hints(h))
        lines.append(
            f"{h.hotel_no}  {h.name}\n"
            f"          {h.address}  |  {coords}  |  {reviews}"
            f"{'  |  ' + baths if baths else ''}\n"
            f"          nearest: {h.nearest_station or '?'}  |  {h.page_url}"
        )
    return "\n".join(lines)


@mcp.tool()
def check_availability(
    hotel_no: int,
    checkin: str,
    checkout: str,
    adults: int = 2,
    rooms: int = 1,
) -> str:
    """Check whether one specific inn is bookable for given dates, right now.

    An empty result can mean sold out, a calendar that has not opened yet, or
    no plan inventory supplied to Rakuten. Rakuten returns the same 404 for all
    three. Use booking_route to find a verified alternate channel before
    adding a Rakuten watch.

    Each plan leads with the whole party's total for the first night, followed
    by Rakuten's per-person or per-room price where the plan states its unit.
    """
    try:
        ci, co = _stay(checkin, checkout)
        hotels = _rakuten().vacancy(ci, co, hotel_nos=[hotel_no], adults=adults, rooms=rooms)
    except _EXPECTED_FAILURES as error:
        return _failed("Availability check", error)
    nights = (co - ci).days
    if not hotels or not hotels[0].is_available:
        return (
            f"Nothing bookable through Rakuten at {hotel_no} for {checkin} to {checkout}. "
            "It may be sold out, not yet open, or not supplying plan inventory to Rakuten. "
            "Use booking_route to check a verified alternate channel before adding a watch."
        )
    h = hotels[0]
    first_night = "first night only" if nights > 1 else "one night"
    out = [
        f"{h.name} — {len(h.plans)} plan(s), {checkin} → {checkout}, {nights} night(s)",
        f"  Totals: {adults} adult(s), {rooms} room(s), {first_night}.",
    ]
    for p in sorted(h.plans, key=lambda p: p.total or 10**9):
        out.append(
            f"  {yen_kr(p.total)} total{_unit_price(p)}"
            f" · {meals_en(p.with_dinner, p.with_breakfast)}\n"
            f"      {p.room_name} / {p.plan_name}"
        )
        if p.reserve_url:
            out.append(f"      {p.reserve_url}")
    if rooms > 1 and any(p.charge_flag == 1 for p in h.plans):
        out.append(
            "  Unverified: for per-room plans across several rooms, Rakuten's total "
            "may cover one room only."
        )
    return "\n".join(out)


@mcp.tool()
def booking_route(hotel_no: int) -> str:
    """Show verified booking and contact paths for a Rakuten-listed inn.

    Start with check_availability for the exact dates. If Rakuten is empty,
    this returns the reviewed alternate source, its stable external ID when
    known, and the action the traveller can take. Jalan entries need a
    pre-existing Jalan Web Service key for API stock; new keys are not issued.
    This tool never opens a page, sends a message, or books anything.
    """
    return routes.render(hotel_no)


@mcp.tool()
def booking_route_audit() -> str:
    """Report coverage of the local verified booking-route registry.

    It validates the set of reviewed routes, not live availability. Use this
    after updating data/booking_routes.yaml and use booking_route for one inn.
    """
    return routes.audit()


@mcp.tool()
def lodging_detail(hotel_no: int) -> str:
    """Facility detail for one inn: check-in times, bath type, facilities, phone."""
    try:
        hotel = _rakuten().detail(hotel_no)
    except _EXPECTED_FAILURES as error:
        return _failed("Facility lookup", error)
    if hotel is None:
        return f"No Rakuten facility detail for hotelNo {hotel_no}."
    return detail_text(hotel)


@mcp.tool()
def find_food(
    near: str,
    dish: str | None = None,
    radius_m: int = 1200,
    min_rating: float | None = None,
    limit: int = 12,
) -> str:
    """Find restaurants near a place, optionally by dish.

    Google Places data, not Tabelog — there is no active public Tabelog API for
    this use, so each result carries a Tabelog search link to open by hand.
    Results flag places that likely need booking ahead and days they are
    closed. 'likely needs booking' is a heuristic from price and genre.
    """
    try:
        centre, hits = food_search.search_food(
            near, dish=dish, radius_m=radius_m, min_rating=min_rating, limit=limit
        )
    except _EXPECTED_FAILURES as error:
        return _failed("Food search", error)
    return food_search.render(centre, hits, dish=dish)


# --------------------------------------------------------------- shortlist

@mcp.tool()
def shortlist_show(trip: str) -> str:
    """Everything on a trip's shortlist: candidates found but not yet decided on."""
    try:
        return shortlist.render(shortlist.load(trip))
    except ValueError as error:
        return f"Cannot read shortlist: {error}"


@mcp.tool()
def shortlist_add_lodging(
    trip: str,
    hotel_no: int,
    tags: list[str] | None = None,
    notes: str | None = None,
    seen_price_yen: int | None = None,
) -> str:
    """Keep an inn on the trip's shortlist, with an English name looked up for it.

    Rakuten only has Japanese names, so this does one Places lookup to get an
    English name and coordinates — which also links the entry to the map
    pipeline. Promote it into places.yaml later with shortlist_promote.
    """
    try:
        hotel = _rakuten().detail(hotel_no)
    except _EXPECTED_FAILURES as error:
        return _failed("Facility lookup", error)
    if hotel is None:
        return f"hotelNo {hotel_no} not found on Rakuten."

    name_en: str | None = None
    place_id: str | None = None
    lat, lng = hotel.lat, hotel.lng
    try:
        found = geocode(f"{hotel.name} {hotel.address}", language="en")
        gap = distance_km(found.lat, found.lng, hotel.lat, hotel.lng)
        # A match more than 2 km from where Rakuten says the inn is, is a
        # different building. Keep Rakuten's truth and skip the English name.
        if gap is None or gap <= 2.0:
            name_en, place_id = found.name, found.place_id
            lat, lng = found.lat, found.lng
    except Exception:  # enrichment is optional; never fail an add over it
        pass

    entry = shortlist.lodging_entry(
        hotel_no=hotel_no,
        name_en=name_en,
        name_local=hotel.name,
        address=hotel.address,
        lat=lat,
        lng=lng,
        google_place_id=place_id,
        tags=tags,
        notes=notes or hotel.special,
        query=f"hotelNo {hotel_no}",
        review=f"{hotel.review_average} ({hotel.review_count})" if hotel.review_count else None,
        seen_price_yen=seen_price_yen,
        url=hotel.page_url,
    )
    try:
        entry_id, added = shortlist.add(trip, entry)
    except ValueError as error:
        return f"Cannot update shortlist: {error}"
    if not added:
        return f"{entry_id} is already on {trip}'s shortlist."
    return (
        f"Added {entry_id} to {trip} shortlist — {entry['name_en']} {hotel.name}\n"
        f"  rakuten #{hotel_no}"
        + (f", google place {place_id}" if place_id else ", no Places match (name is Japanese)")
    )


@mcp.tool()
def shortlist_add_restaurant(
    trip: str,
    place_id: str,
    category: str = "restaurant",
    tags: list[str] | None = None,
    notes: str | None = None,
) -> str:
    """Keep a restaurant on the trip's shortlist, by its Google place id."""
    try:
        hit = food_search.fetch_place(place_id)
        name_local = food_search.local_name(place_id) if hit is not None else None
    except _EXPECTED_FAILURES as error:
        return _failed("Place lookup", error)
    if hit is None:
        return f"Google Places has no place with id {place_id!r}."
    all_tags = list(tags or [])
    if hit.booking_likely and "booking-needed" not in all_tags:
        all_tags.append("booking-needed")

    entry = shortlist.food_entry(
        name=hit.name,
        name_local=name_local,
        address=hit.address,
        category=category,
        lat=hit.lat,
        lng=hit.lng,
        google_place_id=place_id,
        tags=all_tags,
        notes=notes,
        query=f"places/{place_id}",
        review=f"{hit.rating} ({hit.rating_count})" if hit.rating_count else None,
        url=hit.maps_uri,
    )
    try:
        entry_id, added = shortlist.add(trip, entry)
    except ValueError as error:
        return f"Cannot update shortlist: {error}"
    if not added:
        return f"{entry_id} is already on {trip}'s shortlist."
    closed = f", closed {'/'.join(hit.closed_days)}" if hit.closed_days else ""
    return f"Added {entry_id} to {trip} shortlist — {hit.name}{closed}"


@mcp.tool()
def shortlist_promote(trip: str, entry_id: str) -> str:
    """Move a shortlist entry into the trip's places.yaml, where it becomes real.

    After this, sync_trip picks it up like any hand-written place and it appears
    on the generated map.
    """
    try:
        promoted = shortlist.promote(trip, entry_id)
    except ValueError as e:
        return str(e)
    if promoted is None:
        return f"{entry_id!r} is not on {trip}'s shortlist."
    return (
        f"Promoted {entry_id} into trips/{trip}/places.yaml. "
        "Run sync_trip, then generate_trip_map when you want fresh artifacts."
    )


# ----------------------------------------------------------------- watching

@mcp.tool()
def watch_add(
    hotel_no: int,
    label: str,
    checkin: str | None = None,
    checkout: str | None = None,
    window_start: str | None = None,
    window_end: str | None = None,
    nights: int = 1,
    adults: int = 2,
    rooms: int = 1,
    max_yen: int | None = None,
    trip: str | None = None,
    place_id: str | None = None,
) -> str:
    """Watch an inn and report when it becomes bookable.

    Use this only after the inn has demonstrated that it publishes inventory
    through Rakuten. It is useful when that channel has not opened its calendar
    yet — typically three to six months ahead for small ryokan.

    Either give exact checkin/checkout, or a window plus nights, which creates
    one watch per candidate check-in date. Use a window when the dates are
    still moving. max_yen caps the whole party's first-night total, the same
    number find_lodging and check_availability lead with.
    """
    conn = _obs()
    if window_start and window_end:
        try:
            ids = watch.add_window(
                conn, hotel_no=hotel_no, label=label,
                window_start=date.fromisoformat(window_start),
                window_end=date.fromisoformat(window_end),
                nights=nights, adults=adults, rooms=rooms,
                trip_id=trip, place_id=place_id, max_charge=max_yen,
            )
        except ValueError as error:
            return f"Cannot add watch: {error}"
        return (
            f"Watching {label} across {window_start}→{window_end}, {nights}-night stays: "
            f"{len(ids)} date(s). Run watch_run to poll."
        )
    if not (checkin and checkout):
        return "Give either checkin and checkout, or window_start, window_end and nights."
    try:
        ci, co = _stay(checkin, checkout)
    except ValueError as error:
        return f"Cannot add watch: {error}"
    target_id, created = watch.add_target(
        conn, hotel_no=hotel_no, label=label, checkin=ci, checkout=co,
        adults=adults, rooms=rooms, trip_id=trip, place_id=place_id, max_charge=max_yen,
    )
    verb = "Watching" if created else "Already watching"
    return f"{verb} #{target_id}: {label}, {checkin} → {checkout}, {adults} adult(s)."


@mcp.tool()
def watch_list(trip: str | None = None) -> str:
    """Every active watch and its most recent observed state."""
    targets = watch.list_targets(_obs(), trip_id=trip)
    if not targets:
        return "No active watches."
    return "\n".join(t.describe() for t in targets)


@mcp.tool()
def watch_run() -> str:
    """Poll every watch once and report what changed since the last poll.

    Normally run on a schedule rather than interactively — the value is in the
    diff between days. Use watch_news to read what the scheduled runs found.
    """
    try:
        changes = watch.poll(_obs(), _rakuten())
        incomplete = ""
    except watch.PollError as error:
        # The other batches were still polled; report what they found too.
        changes, incomplete = error.changes, f"\n\nIncomplete run: {error}"
    except _EXPECTED_FAILURES as error:
        return _failed("Watch run", error)
    found = "\n".join(str(c) for c in changes) if changes else "No changes."
    return found + incomplete


@mcp.tool()
def watch_news(mark_seen: bool = True) -> str:
    """What the scheduled watch runs have found since you last looked."""
    conn = _obs()
    unseen = watch.unseen_changes(conn)
    if not unseen:
        runs = watch.last_runs(conn, limit=1)
        if not runs:
            return "Nothing new. No watch run has happened yet."
        last = runs[0]
        return (
            f"Nothing new. Last run {last['started_at'][:16].replace('T', ' ')} UTC, "
            f"{last['targets_polled']} target(s) polled"
            + (f", error: {last['error']}" if last["error"] else ".")
        )
    if mark_seen:
        watch.mark_seen(conn, [i for i, _ in unseen])
    return "\n".join(line for _, line in unseen)


if __name__ == "__main__":
    mcp.run()
