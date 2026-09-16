"""travel-planner CLI entry point."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from dotenv import load_dotenv

if TYPE_CHECKING:
    from travel_planner.lodging.rakuten import RakutenTravel

from travel_planner import trips as trip_service
from travel_planner.logging_setup import quiet_http_logging
from travel_planner.paths import observations_db_path, planning_db_path
from travel_planner.paths import repo_root as _paths_repo_root
from travel_planner.schema import SCHEMA_DDL

# Load the repo-root .env wherever `tp` is started from (launchd, another cwd),
# the same file the MCP server loads.
load_dotenv(_paths_repo_root() / ".env")
quiet_http_logging()   # Rakuten keys ride in the query string; see logging_setup

app = typer.Typer(no_args_is_help=True, help="travel-planner: trip markdown → My Maps CSV.")
map_app = typer.Typer(no_args_is_help=True, help="Map artifact commands.")
lodging_app = typer.Typer(no_args_is_help=True, help="Lodging search via Rakuten Travel.")
food_app = typer.Typer(no_args_is_help=True, help="Restaurant search via Google Places.")
shortlist_app = typer.Typer(no_args_is_help=True, help="Per-trip candidate shortlist.")
watch_app = typer.Typer(no_args_is_help=True, help="Availability watches.")
app.add_typer(map_app, name="map")
app.add_typer(lodging_app, name="lodging")
app.add_typer(food_app, name="food")
app.add_typer(shortlist_app, name="shortlist")
app.add_typer(watch_app, name="watch")


def _repo_root() -> Path:
    return _paths_repo_root()


def _db_path() -> Path:
    return planning_db_path()


def _resolve_slug_or_exit(input_slug: str) -> str:
    """Fuzzy-resolve a trip slug. Exits 1 with a helpful message on miss/ambiguity."""
    from travel_planner.resolve import list_trips, resolve_slug

    trips = list_trips(_repo_root() / "trips")
    slug, candidates = resolve_slug(input_slug, trips)
    if slug is not None:
        if slug != input_slug:
            typer.secho(f"  resolved {input_slug!r} → {slug!r}", fg=typer.colors.BLUE)
        return slug
    if candidates:
        typer.secho(
            f"Multiple trips match {input_slug!r}: {', '.join(candidates)}",
            fg=typer.colors.RED,
        )
    else:
        available = ", ".join(trips) if trips else "(no trips yet)"
        typer.secho(
            f"No trip matches {input_slug!r}. Available: {available}",
            fg=typer.colors.RED,
        )
    raise typer.Exit(1)


def _public_ip() -> str | None:
    """Current egress IP, for comparing against the Rakuten app's allowlist."""
    import requests

    try:
        resp = requests.get("https://api.ipify.org", timeout=5)
        return resp.text.strip() if resp.status_code == 200 else None
    except Exception:
        return None


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

    app_id = os.getenv("RAKUTEN_APP_ID")
    access_key = os.getenv("RAKUTEN_ACCESS_KEY")
    if not app_id or not access_key:
        warnings.append(
            "RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY not both set; lodging search will fail. "
            "Both are issued at https://webservice.rakuten.co.jp/app/list"
        )
    else:
        typer.echo(f"  ok    Rakuten keys set (app {len(app_id)} chars, key {len(access_key)})")
        # The Rakuten app is IP-allowlisted and our address is a dynamic
        # residential lease, so this is the check that turns a baffling 400
        # into an obvious one.
        ip = _public_ip()
        if ip is None:
            warnings.append("Could not determine your public IP (offline?)")
        else:
            typer.echo(f"  ok    public IP {ip}")
            typer.echo("        must match the app's allowlist — a VPN or an ISP")
            typer.echo("        lease change breaks Rakuten calls until it's updated")

    obs_path = observations_db_path()
    if obs_path.exists():
        with sqlite3.connect(obs_path) as obs_conn:
            n_watch = obs_conn.execute(
                "SELECT count(*) FROM watch_target WHERE active = 1"
            ).fetchone()[0]
            n_unseen = obs_conn.execute(
                "SELECT count(*) FROM change_log WHERE seen = 0"
            ).fetchone()[0]
        typer.echo(
            f"  ok    observations.db: {n_watch} active watch(es), "
            f"{n_unseen} unread change(s)"
        )
    else:
        typer.echo("  ok    observations.db not created yet (no watches)")

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
    """Validate and sync a trip. The MCP tool is the normal user-facing route."""
    try:
        report = trip_service.sync_trip(
            slug,
            root=_repo_root(),
            lookup=not no_lookup,
            force_lookup=force,
        )
    except trip_service.TripError as error:
        typer.secho(f"Parse error: {error}", fg=typer.colors.RED)
        raise typer.Exit(1) from error

    slug = report.validation.slug
    if report.enrichment is not None and report.enrichment.needed_lookup:
        enrichment = report.enrichment
        typer.echo(
            f"  lookup: tried {enrichment.needed_lookup} → "
            f"{enrichment.new_matches} matched, "
            f"{enrichment.cache_hits} from cache, "
            f"{len(enrichment.misses)} missed; "
            f"{enrichment.updates_applied} yaml update(s)"
        )
    elif report.lookup_skipped_reason:
        typer.secho(f"  warn: {report.lookup_skipped_reason}", fg=typer.colors.YELLOW)

    typer.secho(
        f"Parsed {slug}: trip + {len(report.validation.places)} place(s) + "
        f"{len(report.validation.days)} day(s) "
        f"({report.validation.day_place_count} day-place link(s)) synced.",
        fg=typer.colors.GREEN,
    )
    if report.missing_place_ids:
        typer.secho(
            f"  {report.missing_place_ids} place(s) still missing lat/lng/place_id "
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


@map_app.command("generate")
def map_generate(slug: str) -> None:
    """Generate output artifacts for a trip (CSV, KML, daily routes, indexes).

    Requires the trip to be parsed first (`tp parse <slug>`). Writes to
    `trips/<slug>/output/`.
    """
    try:
        report = trip_service.generate_trip_map(slug, root=_repo_root())
        resolved_slug = trip_service.resolve_trip_slug(slug, _repo_root())
    except (trip_service.TripError, ValueError) as error:
        typer.secho(str(error), fg=typer.colors.RED)
        raise typer.Exit(1) from error

    typer.secho(
        f"Generated {len(report.files_written)} file(s) in trips/{resolved_slug}/output/",
        fg=typer.colors.GREEN,
    )
    typer.echo(
        f"  {report.places_pinned}/{report.places_total} place(s) pinned, "
        f"{report.places_saveable} saveable, "
        f"{report.days_with_routes} day(s) with routes"
    )


@map_app.command("register-url")
def map_register_url(slug: str, url: str) -> None:
    """Store the My Maps URL for a trip after you've imported the CSV.

    Run this once after the manual My Maps import so `tp map open <slug>`
    knows where to send you. The URL is written to trip.md's frontmatter, so
    re-parsing the trip keeps it.
    """
    try:
        resolved = trip_service.register_map_url(slug, url, _repo_root())
    except trip_service.TripError as error:
        typer.secho(str(error), fg=typer.colors.RED)
        raise typer.Exit(1) from error
    typer.secho(f"Registered map URL for {resolved} in trips/{resolved}/trip.md.",
                fg=typer.colors.GREEN)
    typer.echo(f"  {url}")


@map_app.command("open")
def map_open(slug: str) -> None:
    """Open the trip's registered My Maps URL in your default browser."""
    import webbrowser

    try:
        resolved, url = trip_service.map_url(slug, _repo_root())
    except trip_service.TripError as error:
        typer.secho(str(error), fg=typer.colors.RED)
        raise typer.Exit(1) from error
    if not url:
        typer.secho(
            f"No map URL registered for {resolved}. "
            f"Run `tp map register-url {resolved} <url>` after importing the CSV.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    typer.echo(f"Opening {url}")
    webbrowser.open(url)


@app.command("trips")
def list_trips_cmd() -> None:
    """List all trips found under `trips/`."""
    from travel_planner.resolve import list_trips

    trips = list_trips(_repo_root() / "trips")
    if not trips:
        typer.echo("(no trips yet — create one under trips/<slug>/)")
        return
    for slug in trips:
        typer.echo(slug)


# ------------------------------------------------------------------ lodging


def _rakuten_client() -> RakutenTravel:
    from travel_planner.lodging.rakuten import RakutenError, RakutenTravel

    try:
        return RakutenTravel()
    except RakutenError as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1) from e


@lodging_app.command("search")
def lodging_search(
    where: str,
    checkin: str = typer.Option(..., "--checkin", help="YYYY-MM-DD"),
    checkout: str = typer.Option("", "--checkout", help="YYYY-MM-DD (or use --nights)"),
    nights: int = typer.Option(1, "--nights", help="Used when --checkout is omitted."),
    adults: int = typer.Option(2, "--adults"),
    rooms: int = typer.Option(1, "--rooms"),
    radius_km: float = typer.Option(3.0, "--radius-km", help="Rakuten caps this at 3.0."),
    max_yen: int | None = typer.Option(
        None, "--max-yen", help="Ceiling on the whole party's first-night total, yen."
    ),
    onsen: bool = typer.Option(False, "--onsen", help="Hot-spring inns only."),
    with_dinner: bool = typer.Option(False, "--dinner", help="Half-board plans only."),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    """Find bookable lodging near a place: `tp lodging search "Kinosaki Onsen" --checkin ...`"""
    from datetime import date as date_t
    from datetime import timedelta

    from travel_planner.geo import GeocodeError
    from travel_planner.lodging.rakuten import RakutenError
    from travel_planner.lodging.search import render, search_near

    ci = date_t.fromisoformat(checkin)
    co = date_t.fromisoformat(checkout) if checkout else ci + timedelta(days=nights)
    try:
        centre, hits = search_near(
            _rakuten_client(), where, ci, co,
            radius_km=radius_km, adults=adults, rooms=rooms, max_charge=max_yen,
            onsen=onsen, with_dinner=with_dinner, limit=limit,
        )
    except (GeocodeError, RakutenError) as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1) from e
    typer.echo(render(centre, hits, ci, co, radius_km=min(max(radius_km, 0.1), 3.0)))


@lodging_app.command("resolve")
def lodging_resolve(name: str) -> None:
    """Resolve an inn name to a Rakuten hotelNo. Japanese names work far better."""
    from travel_planner.lodging.search import bath_hints

    hits = _rakuten_client().resolve(name)
    if not hits:
        typer.secho(
            f"No Rakuten listing for {name!r}. Try the Japanese name — and note that "
            "plenty of good minshuku simply don't sell through Rakuten.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)
    for h in hits[:8]:
        baths = ", ".join(bath_hints(h))
        typer.echo(f"{h.hotel_no}  {h.name}")
        typer.echo(f"          {h.address}{'  |  ' + baths if baths else ''}")


@lodging_app.command("show")
def lodging_show(hotel_no: int) -> None:
    """Facility detail for one inn: check-in times, bath, facilities."""
    from travel_planner.lodging.search import detail_text

    hotel = _rakuten_client().detail(hotel_no)
    if hotel is None:
        typer.secho(f"No Rakuten facility detail for hotelNo {hotel_no}.", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.echo(detail_text(hotel))


# --------------------------------------------------------------------- food


@food_app.command("search")
def food_search_cmd(
    near: str,
    dish: str = typer.Option("", "--dish", help="e.g. unagi, sushi, okonomiyaki"),
    radius_m: int = typer.Option(1200, "--radius-m"),
    min_rating: float | None = typer.Option(None, "--min-rating"),
    limit: int = typer.Option(12, "--limit"),
) -> None:
    """Find restaurants near a place: `tp food search "Todai-ji Nara" --dish kamameshi`"""
    from travel_planner.food import search as food_mod
    from travel_planner.geo import GeocodeError

    try:
        centre, hits = food_mod.search_food(
            near, dish=dish or None, radius_m=radius_m, min_rating=min_rating, limit=limit
        )
    except GeocodeError as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1) from e
    typer.echo(food_mod.render(centre, hits, dish=dish or None))


# ---------------------------------------------------------------- shortlist


@shortlist_app.command("list")
def shortlist_list(slug: str) -> None:
    """Show a trip's shortlist of candidates."""
    from travel_planner import shortlist

    slug = _resolve_slug_or_exit(slug)
    typer.echo(shortlist.render(shortlist.load(slug)))


@shortlist_app.command("promote")
def shortlist_promote_cmd(slug: str, entry_id: str) -> None:
    """Move a shortlist entry into places.yaml, where the map pipeline picks it up."""
    from travel_planner import shortlist

    slug = _resolve_slug_or_exit(slug)
    try:
        promoted = shortlist.promote(slug, entry_id)
    except ValueError as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1) from e
    if promoted is None:
        typer.secho(f"{entry_id!r} is not on {slug}'s shortlist.", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.secho(f"Promoted {entry_id} into trips/{slug}/places.yaml", fg=typer.colors.GREEN)
    typer.echo(f"  run `tp parse {slug}` to pick it up")


@shortlist_app.command("remove")
def shortlist_remove_cmd(slug: str, entry_id: str) -> None:
    """Drop a candidate from the shortlist."""
    from travel_planner import shortlist

    slug = _resolve_slug_or_exit(slug)
    if not shortlist.remove(slug, entry_id):
        typer.secho(f"{entry_id!r} is not on {slug}'s shortlist.", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.secho(f"Removed {entry_id} from {slug}'s shortlist.", fg=typer.colors.GREEN)


# ------------------------------------------------------------------- watch


@watch_app.command("add")
def watch_add_cmd(
    hotel_no: int,
    label: str = typer.Option(..., "--label", help="Human name, used in alerts."),
    checkin: str = typer.Option("", "--checkin", help="YYYY-MM-DD"),
    checkout: str = typer.Option("", "--checkout", help="YYYY-MM-DD"),
    window: str = typer.Option("", "--window", help="YYYY-MM-DD..YYYY-MM-DD"),
    nights: int = typer.Option(1, "--nights", help="Stay length, with --window."),
    adults: int = typer.Option(2, "--adults"),
    rooms: int = typer.Option(1, "--rooms"),
    max_yen: int | None = typer.Option(
        None, "--max-yen", help="Ceiling on the whole party's first-night total, yen."
    ),
    trip: str = typer.Option("", "--trip"),
    place_id: str = typer.Option("", "--place-id", help="Slug in the trip's places.yaml."),
) -> None:
    """Watch an inn for dates, or across a window while dates are still moving."""
    from datetime import date as date_t

    from travel_planner.lodging import observations
    from travel_planner.lodging import watch as watch_mod

    trip_slug = _resolve_slug_or_exit(trip) if trip else None
    conn = observations.connect()
    if window:
        try:
            start_s, end_s = window.split("..")
        except ValueError as e:
            typer.secho("--window must look like 2027-02-25..2027-03-15", fg=typer.colors.RED)
            raise typer.Exit(1) from e
        ids = watch_mod.add_window(
            conn, hotel_no=hotel_no, label=label,
            window_start=date_t.fromisoformat(start_s), window_end=date_t.fromisoformat(end_s),
            nights=nights, adults=adults, rooms=rooms,
            trip_id=trip_slug, place_id=place_id or None, max_charge=max_yen,
        )
        typer.secho(
            f"Watching {label} across {start_s}→{end_s} in {nights}-night stays "
            f"({len(ids)} date(s)).",
            fg=typer.colors.GREEN,
        )
        return
    if not (checkin and checkout):
        typer.secho(
            "Give --checkin and --checkout, or --window with --nights.", fg=typer.colors.RED
        )
        raise typer.Exit(1)
    target_id, created = watch_mod.add_target(
        conn, hotel_no=hotel_no, label=label,
        checkin=date_t.fromisoformat(checkin), checkout=date_t.fromisoformat(checkout),
        adults=adults, rooms=rooms, trip_id=trip_slug, place_id=place_id or None,
        max_charge=max_yen,
    )
    verb = "Watching" if created else "Already watching"
    typer.secho(f"{verb} #{target_id}: {label}, {checkin} → {checkout}", fg=typer.colors.GREEN)


@watch_app.command("list")
def watch_list_cmd(
    trip: str = typer.Option("", "--trip"),
    all_targets: bool = typer.Option(False, "--all", help="Include deactivated watches."),
) -> None:
    """Every watch and its most recent observed state."""
    from travel_planner.lodging import observations
    from travel_planner.lodging import watch as watch_mod

    trip_slug = _resolve_slug_or_exit(trip) if trip else None
    targets = watch_mod.list_targets(
        observations.connect(), trip_id=trip_slug, include_inactive=all_targets
    )
    if not targets:
        typer.echo("No active watches.")
        return
    for t in targets:
        typer.echo(t.describe())


@watch_app.command("remove")
def watch_remove_cmd(target_id: int) -> None:
    """Deactivate a watch, keeping its history."""
    from travel_planner.lodging import observations
    from travel_planner.lodging import watch as watch_mod

    if not watch_mod.remove_target(observations.connect(), target_id):
        typer.secho(f"No watch with id {target_id}.", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.secho(f"Deactivated watch #{target_id}.", fg=typer.colors.GREEN)


@watch_app.command("run")
def watch_run_cmd(
    quiet: bool = typer.Option(False, "--quiet", help="Print only when something changed."),
) -> None:
    """Poll every watch once and report changes. This is what the schedule runs."""
    from travel_planner.lodging import observations
    from travel_planner.lodging import watch as watch_mod

    failure: watch_mod.PollError | None = None
    try:
        changes = watch_mod.poll(observations.connect(), _rakuten_client())
    except watch_mod.PollError as error:
        changes, failure = error.changes, error
    if not changes and not quiet:
        typer.echo("No changes.")
    # A first run over a two-week window is dozens of changes at once; the URLs
    # turn that into an unreadable wall. Details stay one command away.
    compact = len(changes) > 8
    for c in changes:
        colour = typer.colors.GREEN if c.kind == "opened" else typer.colors.YELLOW
        typer.secho(c.headline if compact else str(c), fg=colour)
    if compact:
        typer.echo(f"\n{len(changes)} changes. `tp watch log` for the booking links.")
    if failure is not None:
        typer.secho(f"Incomplete run: {failure}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)


@watch_app.command("log")
def watch_log_cmd(
    keep_unseen: bool = typer.Option(False, "--keep-unseen", help="Don't mark them as seen."),
) -> None:
    """What the scheduled runs found since you last looked."""
    from travel_planner.lodging import observations
    from travel_planner.lodging import watch as watch_mod

    conn = observations.connect()
    unseen = watch_mod.unseen_changes(conn)
    if not unseen:
        runs = watch_mod.last_runs(conn, limit=1)
        if not runs:
            typer.echo("Nothing new. No watch run has happened yet.")
            return
        last = runs[0]
        stamp = last["started_at"][:16].replace("T", " ")
        typer.echo(f"Nothing new. Last run {stamp} UTC, {last['targets_polled']} target(s).")
        if last["error"]:
            typer.secho(f"  last run errored: {last['error']}", fg=typer.colors.RED)
        return
    for _, line in unseen:
        typer.echo(line)
    if not keep_unseen:
        watch_mod.mark_seen(conn, [i for i, _ in unseen])


if __name__ == "__main__":
    app()
