"""Tests for the service layer that powers both MCP and the maintenance CLI."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from travel_planner.trips import (
    TripError,
    day_view,
    generate_trip_map,
    map_url,
    register_map_url,
    sync_trip,
    validate_trip,
)


def _trip(root: Path, *, dangling: bool = False) -> None:
    trip_dir = root / "trips" / "demo-2027-01"
    (trip_dir / "days").mkdir(parents=True)
    trip_dir.joinpath("trip.md").write_text(
        "---\ntrip_id: demo-2027-01\nname: Demo Trip\n---\n",
        encoding="utf-8",
    )
    trip_dir.joinpath("places.yaml").write_text(
        "- id: demo-onsen\n"
        "  name_en: Demo Onsen\n"
        "  name_local: デモ温泉\n"
        "  category: onsen\n"
        "  lat: 35.0\n"
        "  lng: 135.0\n"
        "  source_refs:\n"
        "    openstreetmap: node/1\n",
        encoding="utf-8",
    )
    ref = "missing-place" if dangling else "demo-onsen"
    trip_dir.joinpath("days/day-01.md").write_text(
        f"---\nday_number: 1\nlocation: Demo\n---\nVisit [[{ref}]].\n",
        encoding="utf-8",
    )


def test_validate_reports_dangling_day_reference(tmp_path: Path) -> None:
    _trip(tmp_path, dangling=True)
    report = validate_trip("demo", tmp_path)
    assert report.ok is False
    assert report.errors == [
        "day-01.md references [[missing-place]] but no such place in places.yaml"
    ]


def test_sync_and_generate_use_canonical_markdown(tmp_path: Path) -> None:
    _trip(tmp_path)
    report = sync_trip("demo", root=tmp_path, lookup=False)
    assert report.validation.ok
    assert report.lookup_skipped_reason == "lookup disabled"
    assert report.missing_place_ids == 1

    with sqlite3.connect(tmp_path / "data" / "travel_planner.db") as conn:
        source_refs = conn.execute("SELECT source_refs_json FROM place").fetchone()[0]
    assert source_refs == '{"openstreetmap": "node/1"}'

    generated = generate_trip_map("demo", tmp_path)
    assert {path.name for path in generated.files_written} == {
        "README.md",
        "daily-routes.md",
        "my-maps.csv",
        "my-maps.kml",
        "places-index.md",
        "saveable-places.md",
    }


def test_sync_rejects_invalid_trip(tmp_path: Path) -> None:
    _trip(tmp_path, dangling=True)
    with pytest.raises(TripError, match="missing-place"):
        sync_trip("demo", root=tmp_path, lookup=False)


MAP_URL = "https://www.google.com/maps/d/edit?mid=demo"


def test_registered_map_url_lives_in_trip_md_and_survives_resync(tmp_path: Path) -> None:
    _trip(tmp_path)
    sync_trip("demo", root=tmp_path, lookup=False)
    trip_md = tmp_path / "trips" / "demo-2027-01" / "trip.md"
    trip_md.write_text(trip_md.read_text(encoding="utf-8") + "\n# Demo\n\nProse.\n")

    assert register_map_url("demo", MAP_URL, tmp_path) == "demo-2027-01"
    text = trip_md.read_text(encoding="utf-8")
    assert text.endswith("---\n\n# Demo\n\nProse.\n")          # body untouched
    assert f"my_maps_url: {MAP_URL}\n---" in text

    sync_trip("demo", root=tmp_path, lookup=False)                  # used to wipe it
    with sqlite3.connect(tmp_path / "data" / "travel_planner.db") as conn:
        assert conn.execute("SELECT my_maps_url FROM trip").fetchone() == (MAP_URL,)
    assert map_url("demo", tmp_path) == ("demo-2027-01", MAP_URL)


def test_register_map_url_rejects_non_url(tmp_path: Path) -> None:
    _trip(tmp_path)
    with pytest.raises(TripError, match="Not a map URL"):
        register_map_url("demo", "mid=demo", tmp_path)


def test_yaml_syntax_error_is_a_validation_error_not_a_traceback(tmp_path: Path) -> None:
    _trip(tmp_path)
    places = tmp_path / "trips" / "demo-2027-01" / "places.yaml"
    places.write_text("- id: demo-onsen\n  name_en: [unclosed\n", encoding="utf-8")
    report = validate_trip("demo", tmp_path)
    assert report.ok is False
    assert "line" in report.errors[0]


def test_day_view_reads_current_markdown_not_the_last_sync(tmp_path: Path) -> None:
    _trip(tmp_path)
    trip_dir = tmp_path / "trips" / "demo-2027-01"
    with trip_dir.joinpath("places.yaml").open("a", encoding="utf-8") as f:
        f.write("- id: demo-temple\n  name_en: Demo Temple\n  category: temple\n")
    day = trip_dir / "days" / "day-01.md"
    day.write_text("---\nday_number: 1\n---\n[[demo-onsen]] then [[demo-temple]].\n")
    sync_trip("demo", root=tmp_path, lookup=False)

    day.write_text("---\nday_number: 1\n---\n[[demo-temple]] then [[demo-onsen]].\n")
    view = day_view("demo", 1, tmp_path)
    assert view is not None
    assert [link.place.id for link in view.links] == ["demo-temple", "demo-onsen"]
    assert view.links[1].place.lat == 35.0
    assert day_view("demo", 2, tmp_path) is None
