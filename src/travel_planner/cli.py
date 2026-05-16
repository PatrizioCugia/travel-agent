"""travel-planner CLI entry point."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import typer
from dotenv import load_dotenv

from travel_planner.schema import SCHEMA_DDL

# Auto-load .env from cwd or a parent so GOOGLE_MAPS_API_KEY can live in the
# repo root without manual `export`.
load_dotenv()

app = typer.Typer(no_args_is_help=True, help="travel-planner: trip markdown → My Maps CSV.")


def _repo_root() -> Path:
    cur = Path.cwd().resolve()
    for parent in [cur, *cur.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return cur


def _db_path() -> Path:
    return _repo_root() / "data" / "travel_planner.db"


@app.command()
def doctor() -> None:
    """Health check: Python version, API key, DB path, schema reachability."""
    errors: list[str] = []
    warnings: list[str] = []

    py = sys.version_info
    if (py.major, py.minor) < (3, 12):
        errors.append(f"Python 3.12+ required; running {py.major}.{py.minor}")
    else:
        typer.echo(f"  ok    Python {py.major}.{py.minor}.{py.micro}")

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        warnings.append("GOOGLE_MAPS_API_KEY not set; live lookups will fail")
    else:
        typer.echo(f"  ok    GOOGLE_MAPS_API_KEY set ({len(api_key)} chars)")

    db_path = _db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(db_path) as conn:
            conn.executescript(SCHEMA_DDL)
        typer.echo(f"  ok    DB writeable at {db_path.relative_to(_repo_root())}")
    except Exception as e:
        errors.append(f"DB unreachable at {db_path}: {e}")

    trips_dir = _repo_root() / "trips"
    if not trips_dir.exists():
        warnings.append(f"trips/ does not exist at {trips_dir}")
    else:
        n = sum(1 for p in trips_dir.iterdir() if p.is_dir() and not p.name.startswith("_"))
        typer.echo(f"  ok    trips/ exists ({n} trip(s) excluding _template)")

    if warnings:
        typer.echo("")
        for w in warnings:
            typer.secho(f"  warn  {w}", fg=typer.colors.YELLOW)
    if errors:
        typer.echo("")
        for err in errors:
            typer.secho(f"  fail  {err}", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.echo("")
    typer.secho("doctor: ok", fg=typer.colors.GREEN)


@app.command()
def parse(
    slug: str,
    no_lookup: bool = typer.Option(
        False,
        "--no-lookup",
        help="Skip Places API lookup; just parse what's in the YAML.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Re-lookup every place, overriding existing lat/lng/place_id.",
    ),
) -> None:
    """Parse a trip's markdown into the DB. Fills missing lat/lng via Places API.

    The trip directory must be `trips/<slug>/` and the frontmatter's
    `trip_id` must match `<slug>`. Without `--no-lookup`, places missing
    lat/lng/google_place_id are looked up via Places API (New) and written
    back to places.yaml (formatting + comments preserved).
    """
    from pydantic import ValidationError

    from travel_planner.db.sync import sync_trip
    from travel_planner.maps.cache import PlacesCache
    from travel_planner.maps.enrich import enrich_places, write_misses_report
    from travel_planner.parser.day import load_days, validate_day_refs
    from travel_planner.parser.places import load_places
    from travel_planner.parser.trip import load_trip_frontmatter

    repo_root = _repo_root()
    trip_dir = repo_root / "trips" / slug
    if not trip_dir.is_dir():
        typer.secho(f"Trip directory not found: {trip_dir}", fg=typer.colors.RED)
        raise typer.Exit(1)

    places_yaml = trip_dir / "places.yaml"
    trip_md = trip_dir / "trip.md"
    days_dir = trip_dir / "days"

    try:
        trip = load_trip_frontmatter(trip_md, repo_root=repo_root)
        places = load_places(places_yaml)
        days = load_days(days_dir, repo_root)
    except (FileNotFoundError, ValueError, ValidationError) as e:
        typer.secho(f"Parse error: {e}", fg=typer.colors.RED)
        raise typer.Exit(1) from e

    ref_errors = validate_day_refs(days, {p.id for p in places})
    if ref_errors:
        for err in ref_errors:
            typer.secho(f"  dangling ref: {err}", fg=typer.colors.RED)
        raise typer.Exit(1)

    if trip.trip_id != slug:
        typer.secho(
            f"trip_id mismatch: frontmatter has {trip.trip_id!r}, directory is {slug!r}",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not no_lookup and api_key:
        cache = PlacesCache(_repo_root() / "data" / "places_cache.json")
        report = enrich_places(places, places_yaml, cache, api_key=api_key, force=force)
        if report.needed_lookup:
            typer.echo(
                f"  lookup: tried {report.needed_lookup} → "
                f"{report.new_matches} matched, "
                f"{report.cache_hits} from cache, "
                f"{len(report.misses)} missed; "
                f"{report.updates_applied} yaml update(s)"
            )
        if report.misses:
            misses_path = trip_dir / "output" / "lookup-misses.md"
            write_misses_report(report.misses, misses_path)
            typer.secho(
                f"  misses logged to {misses_path.relative_to(_repo_root())}",
                fg=typer.colors.YELLOW,
            )
        # Re-load with enriched fields
        places = load_places(places_yaml)
    elif not no_lookup and not api_key:
        typer.secho(
            "  warn: GOOGLE_MAPS_API_KEY not set; skipping lookup",
            fg=typer.colors.YELLOW,
        )

    with sqlite3.connect(_db_path()) as conn:
        sync_trip(conn, trip, places, days)

    missing = sum(1 for p in places if not (p.lat and p.lng and p.google_place_id))
    day_place_count = sum(len(d.place_refs) for d in days)
    typer.secho(
        f"Parsed {slug}: trip + {len(places)} place(s) + "
        f"{len(days)} day(s) ({day_place_count} day-place link(s)) synced.",
        fg=typer.colors.GREEN,
    )
    if missing:
        typer.secho(
            f"  {missing} place(s) still missing lat/lng/place_id "
            "— see output/lookup-misses.md or edit places.yaml.",
            fg=typer.colors.YELLOW,
        )


@app.command()
def spike() -> None:
    """End-to-end spine spike: one Places API call → one-row CSV at /tmp/spike.csv.

    Requires GOOGLE_MAPS_API_KEY. Validates the spine before M2+.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        typer.secho("GOOGLE_MAPS_API_KEY not set in environment", fg=typer.colors.RED)
        raise typer.Exit(1)

    from requests.exceptions import HTTPError

    from travel_planner.maps.places_lookup import lookup_place

    query_name = "Atsuta Houraiken main shop"
    query_addr = "503 Godo-cho, Atsuta-ku, Nagoya"
    typer.echo(f"Looking up: {query_name!r} @ {query_addr!r}")

    try:
        result = lookup_place(query_name, query_addr, api_key)
    except HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        body = e.response.text if e.response is not None else "(no response body)"
        typer.secho(f"\nPlaces API error: HTTP {status}", fg=typer.colors.RED)
        typer.echo("Response body:")
        typer.echo(body)
        typer.echo("\nLikely causes (check in order):")
        typer.echo(
            "  1. Places API (New) not enabled — https://console.cloud.google.com/apis/enabled"
        )
        typer.echo("     Make sure 'Places API (New)' is listed (NOT just 'Places API').")
        typer.echo(
            "  2. Key restricted to wrong API — https://console.cloud.google.com/apis/credentials"
        )
        typer.echo("     Edit key → API restrictions → 'Places API (New)' must be checked.")
        typer.echo("  3. Billing not yet active — https://console.cloud.google.com/billing")
        typer.echo("  4. Key just created — wait 2-5 min and retry.")
        raise typer.Exit(1) from e

    if not result:
        typer.secho("No result from Places API", fg=typer.colors.RED)
        raise typer.Exit(1)

    typer.echo(f"  Resolved name:    {result.get('name')}")
    typer.echo(f"  Resolved address: {result.get('formatted_address')}")
    typer.echo(f"  Coordinates:      {result.get('lat')},{result.get('lng')}")
    typer.echo(f"  place_id:         {result.get('place_id')}")

    # CSV schema follows agent A's research (see M1-findings.md):
    # UTF-8 no BOM, LF newlines, RFC-4180 quoting; lat/lng provided to skip
    # the My Maps geocoder; `category` column is the styling hook post-import.
    # `name` is Western-script (My Maps pin title); `name_local` carries the
    # kanji for taxi-driver / staff use — see [[user-csv-presentation-prefs]].
    out = _repo_root() / "spike.csv"
    name_local = (result.get("name") or "").replace('"', '""')
    addr = (result.get("formatted_address") or query_addr).replace('"', '""')
    place_id = result.get("place_id") or ""
    desc = "1873 inventor of hitsumabushi. Walk-in only; 30-60 min wait on weekends."
    tabelog = "https://tabelog.com/en/aichi/A2301/A230112/23000063/"
    header = (
        "name,name_local,latitude,longitude,address,category,day,time_slot,"
        "description,website,tabelog_url,google_place_id"
    )
    row = (
        f'"{query_name}","{name_local}",{result.get("lat")},{result.get("lng")},'
        f'"{addr}",restaurant,2,brunch,"{desc}",,{tabelog},"{place_id}"'
    )
    out.write_text(f"{header}\n{row}\n", encoding="utf-8")
    typer.secho(f"\nWrote {out}.", fg=typer.colors.GREEN)
    typer.echo("Next: open Google My Maps → Create new map → Import → upload this CSV.")
    typer.echo("  - Pick `name` as the title column")
    typer.echo("  - Pick `latitude` + `longitude` as the location columns (skips geocoder)")
    typer.echo("Report back: did the pin land where expected? What did the info-card show?")


if __name__ == "__main__":
    app()
