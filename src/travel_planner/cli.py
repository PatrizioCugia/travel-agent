"""travel-planner CLI entry point."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import typer

from travel_planner.schema import SCHEMA_DDL

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
def spike() -> None:
    """End-to-end spine spike: one Places API call → one-row CSV at /tmp/spike.csv.

    Requires GOOGLE_MAPS_API_KEY. Validates the spine before M2+.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        typer.secho("GOOGLE_MAPS_API_KEY not set in environment", fg=typer.colors.RED)
        raise typer.Exit(1)

    from travel_planner.maps.places_lookup import lookup_place

    query_name = "Atsuta Houraiken main shop"
    query_addr = "503 Godo-cho, Atsuta-ku, Nagoya"
    typer.echo(f"Looking up: {query_name!r} @ {query_addr!r}")

    result = lookup_place(query_name, query_addr, api_key)
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
    out = Path("/tmp/spike.csv")
    name = (result.get("name") or query_name).replace('"', '""')
    addr = (result.get("formatted_address") or query_addr).replace('"', '""')
    place_id = result.get("place_id") or ""
    desc = "1873 inventor of hitsumabushi. Walk-in only; 30-60 min wait on weekends."
    tabelog = "https://tabelog.com/en/aichi/A2301/A230112/23000063/"
    header = (
        "name,latitude,longitude,address,category,day,time_slot,"
        "description,website,tabelog_url,google_place_id"
    )
    row = (
        f'"{name}",{result.get("lat")},{result.get("lng")},"{addr}",'
        f'restaurant,2,brunch,"{desc}",,{tabelog},"{place_id}"'
    )
    out.write_text(f"{header}\n{row}\n", encoding="utf-8")
    typer.secho(f"\nWrote {out}.", fg=typer.colors.GREEN)
    typer.echo("Next: open Google My Maps → Create new map → Import → upload this CSV.")
    typer.echo("  - Pick `name` as the title column")
    typer.echo("  - Pick `latitude` + `longitude` as the location columns (skips geocoder)")
    typer.echo("Report back: did the pin land where expected? What did the info-card show?")


if __name__ == "__main__":
    app()
