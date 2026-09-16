"""Trip lifecycle services shared by the MCP server and maintenance CLI.

Markdown remains canonical.  This module deliberately owns the operations that
read it, validate cross-references, refresh the regenerable SQLite index, and
generate map artifacts.  Interfaces such as MCP should call these functions;
the Typer commands are only a thin operator-facing wrapper.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError
from ruamel.yaml.error import YAMLError

from travel_planner.db.query import DayPlaceLink, DayView, PlaceView
from travel_planner.db.sync import sync_trip as sync_trip_to_db
from travel_planner.maps.cache import PlacesCache
from travel_planner.maps.enrich import EnrichmentReport, enrich_places, write_misses_report
from travel_planner.maps.yaml_writer import set_frontmatter_field
from travel_planner.output.generate import GenerationReport, generate
from travel_planner.parser.day import ParsedDay, load_days, validate_day_refs
from travel_planner.parser.places import PlaceModel, load_places
from travel_planner.parser.trip import TripFrontmatter, load_trip_frontmatter
from travel_planner.paths import repo_root as default_repo_root
from travel_planner.resolve import list_trips, resolve_slug


class TripError(ValueError):
    """A trip could not be resolved, validated, or prepared for an operation."""


@dataclass(frozen=True)
class TripValidationReport:
    """A markdown-only validation result; it never writes files or SQLite."""

    slug: str
    trip: TripFrontmatter | None = None
    places: list[PlaceModel] = field(default_factory=list)
    days: list[ParsedDay] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def day_place_count(self) -> int:
        return sum(len(day.place_refs) for day in self.days)


@dataclass(frozen=True)
class TripSyncReport:
    """The result of syncing canonical markdown into the regenerable index."""

    validation: TripValidationReport
    enrichment: EnrichmentReport | None
    lookup_skipped_reason: str | None
    missing_place_ids: int


def _root(root: Path | None) -> Path:
    return (root or default_repo_root()).resolve()


def resolve_trip_slug(value: str, root: Path | None = None) -> str:
    """Resolve a user-facing trip reference or raise an actionable error."""
    repo = _root(root)
    available = list_trips(repo / "trips")
    slug, candidates = resolve_slug(value, available)
    if slug is not None:
        return slug
    if candidates:
        raise TripError(f"Multiple trips match {value!r}: {', '.join(candidates)}")
    available_text = ", ".join(available) if available else "(no trips yet)"
    raise TripError(f"No trip matches {value!r}. Available: {available_text}")


def validate_trip(value: str, root: Path | None = None) -> TripValidationReport:
    """Validate a trip's canonical markdown without changing any state."""
    repo = _root(root)
    try:
        slug = resolve_trip_slug(value, repo)
    except TripError as error:
        return TripValidationReport(slug=value, errors=[str(error)])

    trip_dir = repo / "trips" / slug
    try:
        trip = load_trip_frontmatter(trip_dir / "trip.md", repo_root=repo)
        places = load_places(trip_dir / "places.yaml")
        days = load_days(trip_dir / "days", repo)
    except (FileNotFoundError, ValueError, ValidationError, YAMLError) as error:
        # YAMLError is not a ValueError; a hand-edited file with a syntax slip
        # must come back as a report naming the file and line, not a traceback.
        return TripValidationReport(slug=slug, errors=[str(error)])

    errors = validate_day_refs(days, {place.id for place in places})
    if trip.trip_id != slug:
        errors.append(
            f"trip_id mismatch: frontmatter has {trip.trip_id!r}, directory is {slug!r}"
        )
    return TripValidationReport(slug=slug, trip=trip, places=places, days=days, errors=errors)


def sync_trip(
    value: str,
    *,
    root: Path | None = None,
    lookup: bool = True,
    force_lookup: bool = False,
    google_api_key: str | None = None,
) -> TripSyncReport:
    """Validate, optionally enrich, then rebuild one trip in the SQLite index."""
    repo = _root(root)
    validation = validate_trip(value, repo)
    trip = validation.trip
    if not validation.ok or trip is None:
        raise TripError("\n".join(validation.errors))

    places = validation.places
    enrichment: EnrichmentReport | None = None
    lookup_skipped_reason: str | None = None
    api_key = google_api_key or os.environ.get("GOOGLE_MAPS_API_KEY")
    if lookup and api_key:
        places_path = repo / "trips" / validation.slug / "places.yaml"
        cache = PlacesCache(repo / "data" / "places_cache.json")
        enrichment = enrich_places(
            places,
            places_path,
            cache,
            api_key=api_key,
            force=force_lookup,
        )
        if enrichment.misses:
            write_misses_report(
                enrichment.misses,
                repo / "trips" / validation.slug / "output" / "lookup-misses.md",
            )
        places = load_places(places_path)
        validation = TripValidationReport(
            slug=validation.slug,
            trip=trip,
            places=places,
            days=validation.days,
        )
    elif not lookup:
        lookup_skipped_reason = "lookup disabled"
    else:
        lookup_skipped_reason = "GOOGLE_MAPS_API_KEY is not set"

    data_dir = repo / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(data_dir / "travel_planner.db") as conn:
        sync_trip_to_db(conn, trip, places, validation.days)

    missing = sum(
        1 for place in places if place.lat is None or place.lng is None or not place.google_place_id
    )
    return TripSyncReport(
        validation=validation,
        enrichment=enrichment,
        lookup_skipped_reason=lookup_skipped_reason,
        missing_place_ids=missing,
    )


def generate_trip_map(value: str, root: Path | None = None) -> GenerationReport:
    """Generate a trip's map artifacts from its previously synced SQLite index."""
    repo = _root(root)
    slug = resolve_trip_slug(value, repo)
    with sqlite3.connect(repo / "data" / "travel_planner.db") as conn:
        return generate(slug, repo / "trips" / slug / "output", conn)


def day_view(value: str, day_number: int, root: Path | None = None) -> DayView | None:
    """One day as its Markdown stands now, with its place references resolved.

    Read from the validated Markdown rather than the SQLite index, so a day
    reordered since the last sync is assessed as written. Coordinates come from
    places.yaml, where sync_trip's lookup writes them. None if no such day file.
    """
    validation = validate_trip(value, root)
    if not validation.ok:
        raise TripError("\n".join(validation.errors))
    parsed = next(
        (day for day in validation.days if day.frontmatter.day_number == day_number), None
    )
    if parsed is None:
        return None
    places = {place.id: _place_view(place) for place in validation.places}
    return DayView(
        day_number=parsed.frontmatter.day_number,
        date=parsed.frontmatter.date,
        location=parsed.frontmatter.location,
        title=parsed.frontmatter.title,
        notes_path=parsed.notes_path,
        links=[
            DayPlaceLink(
                place=places[ref.place_slug],
                order_in_day=ref.order_in_day,
                time_slot=None,
                notes=None,
            )
            for ref in parsed.place_refs
        ],
    )


def _place_view(place: PlaceModel) -> PlaceView:
    return PlaceView(
        id=place.id,
        name_en=place.name_en,
        name_local=place.name_local,
        category=place.category,
        address=place.address,
        lat=place.lat,
        lng=place.lng,
        google_place_id=place.google_place_id,
        source_refs=dict(place.source_refs),
        tags=list(place.tags),
        urls=dict(place.urls),
        notes=place.notes,
    )


def register_map_url(value: str, url: str, root: Path | None = None) -> str:
    """Record a trip's Google My Maps URL in trip.md, and mirror it into SQLite.

    trip.md frontmatter is the record: sync_trip rebuilds the trip row from it,
    so a URL kept only in SQLite vanished on the next sync. Returns the slug.
    """
    if not url.startswith(("https://", "http://")):
        raise TripError(f"Not a map URL: {url!r}")
    repo = _root(root)
    slug = resolve_trip_slug(value, repo)
    trip_md = repo / "trips" / slug / "trip.md"
    try:
        set_frontmatter_field(trip_md, "my_maps_url", url)
    except (FileNotFoundError, ValueError, YAMLError) as error:
        raise TripError(str(error)) from error

    db_path = repo / "data" / "travel_planner.db"
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            has_trip = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'trip'"
            ).fetchone()
            if has_trip:
                conn.execute("UPDATE trip SET my_maps_url = ? WHERE id = ?", (url, slug))
    return slug


def map_url(value: str, root: Path | None = None) -> tuple[str, str | None]:
    """(slug, registered My Maps URL or None), read from trip.md."""
    repo = _root(root)
    slug = resolve_trip_slug(value, repo)
    try:
        trip = load_trip_frontmatter(repo / "trips" / slug / "trip.md", repo_root=repo)
    except (FileNotFoundError, ValueError, ValidationError, YAMLError) as error:
        raise TripError(str(error)) from error
    return slug, trip.my_maps_url
