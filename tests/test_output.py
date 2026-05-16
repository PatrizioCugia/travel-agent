"""Tests for the output generators. View fixtures built in-memory."""

from __future__ import annotations

import sqlite3
import textwrap
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

from travel_planner.db.query import DayPlaceLink, DayView, PlaceView
from travel_planner.db.sync import sync_trip
from travel_planner.output.csv import render_csv
from travel_planner.output.directions import render_daily_routes
from travel_planner.output.generate import generate
from travel_planner.output.kml import render_kml
from travel_planner.output.places_index import render_places_index
from travel_planner.output.saveable import render_saveable_places
from travel_planner.parser.day import DayFrontmatter, DayPlaceRef, ParsedDay
from travel_planner.parser.places import PlaceModel
from travel_planner.parser.trip import TripFrontmatter
from travel_planner.schema import SCHEMA_DDL


def _cafe() -> PlaceView:
    return PlaceView(
        id="atsuta-houraiken-honten",
        name_en="Atsuta Houraiken main shop",
        name_local="あつた蓬莱軒 本店",
        category="restaurant",
        address="503 Godo-cho, Atsuta-ku, Nagoya",
        lat=35.120169,
        lng=136.906898,
        google_place_id="ChIJtest_houraiken",
        tags=["hitsumabushi", "walk-in"],
        urls={"tabelog": "https://tabelog.com/en/aichi/foo"},
        notes="1873 inventor of hitsumabushi.\nWalk-in only.",
        visit_days=[2],
    )


def _shrine() -> PlaceView:
    return PlaceView(
        id="atsuta-jingu",
        name_en="Atsuta Jingu",
        name_local="熱田神宮",
        category="shrine",
        address="Atsuta-ku, Nagoya",
        lat=35.127358,
        lng=136.908695,
        google_place_id="ChIJtest_jingu",
        visit_days=[2],
    )


def _unmapped_place() -> PlaceView:
    return PlaceView(
        id="ghost-place",
        name_en="Ghost Place",
        name_local=None,
        category="cafe",
        address="Unknown",
        lat=None,
        lng=None,
        google_place_id=None,
    )


# ---------- CSV ----------


def test_csv_columns_and_basic_row() -> None:
    out = render_csv([_cafe()])
    lines = out.splitlines()
    assert lines[0].startswith("name,name_local,latitude,longitude,address,category,day")
    assert "Atsuta Houraiken main shop" in lines[1]
    assert "あつた蓬莱軒 本店" in lines[1]
    assert "35.120169" in lines[1]
    assert "136.906898" in lines[1]
    assert "ChIJtest_houraiken" in lines[1]


def test_csv_skips_places_without_coords() -> None:
    out = render_csv([_cafe(), _unmapped_place()])
    assert out.count("\n") == 2  # header + one data row
    assert "Ghost Place" not in out


def test_csv_quotes_fields_with_commas() -> None:
    p = _cafe()
    p.notes = "Has, commas, in, notes"
    out = render_csv([p])
    # Quoted because comma in description
    assert '"Has, commas, in, notes"' in out


def test_csv_no_bom_utf8_lf() -> None:
    out = render_csv([_cafe()])
    assert not out.startswith("﻿")
    assert "\r\n" not in out


# ---------- KML ----------


def test_kml_well_formed() -> None:
    out = render_kml("Nagoya-2026-11", [_cafe(), _shrine()])
    assert out.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<kml" in out
    assert "</kml>" in out


def test_kml_emits_styles_per_category() -> None:
    out = render_kml("Nagoya-2026-11", [_cafe(), _shrine()])
    assert '<Style id="cat-restaurant">' in out
    assert '<Style id="cat-shrine">' in out


def test_kml_coordinates_are_lng_lat_not_lat_lng() -> None:
    """KML uses longitude,latitude order — easy to get wrong."""
    out = render_kml("X", [_cafe()])
    assert "<coordinates>136.906898,35.120169</coordinates>" in out


def test_kml_escapes_xml_special_chars() -> None:
    p = _cafe()
    p.name_en = "Foo & Bar"
    out = render_kml("X", [p])
    assert "Foo &amp; Bar" in out
    assert "Foo & Bar</name>" not in out


# ---------- Daily routes ----------


def _day_with_places(places: list[PlaceView], day_number: int = 1) -> DayView:
    return DayView(
        day_number=day_number,
        date=date(2026, 1, day_number),
        location="Nagoya",
        title="Test",
        notes_path=None,
        links=[
            DayPlaceLink(place=p, order_in_day=i, time_slot=None, notes=None)
            for i, p in enumerate(places)
        ],
    )


def test_daily_routes_emits_url_with_place_id_waypoints() -> None:
    day = _day_with_places([_cafe(), _shrine()])
    out = render_daily_routes("Nagoya 2026", [day])
    assert "place_id:ChIJtest_houraiken" in out
    assert "place_id:ChIJtest_jingu" in out
    assert "google.com/maps/dir" in out


def test_daily_routes_single_stop_uses_destination() -> None:
    day = _day_with_places([_cafe()])
    out = render_daily_routes("X", [day])
    assert "destination=" in out
    assert "waypoints=" not in out


def test_daily_routes_falls_back_to_coords_when_no_place_id() -> None:
    cafe = _cafe()
    cafe.google_place_id = None
    day = _day_with_places([cafe])
    out = render_daily_routes("X", [day])
    assert "35.120169,136.906898" in out


def test_daily_routes_splits_at_cap() -> None:
    """Days with >9 places split into multiple routes."""
    many = [
        PlaceView(
            id=f"p{i}",
            name_en=f"Place {i}",
            name_local=None,
            category="restaurant",
            address=None,
            lat=35.0 + i * 0.001,
            lng=136.0 + i * 0.001,
            google_place_id=f"ChIJp{i}",
        )
        for i in range(11)
    ]
    day = _day_with_places(many)
    out = render_daily_routes("X", [day])
    assert "Route 1 of 2" in out
    assert "Route 2 of 2" in out


def test_daily_routes_handles_empty_days() -> None:
    out = render_daily_routes("Empty Trip", [])
    assert "No days defined yet" in out


# ---------- Places index ----------


def test_places_index_groups_by_category() -> None:
    out = render_places_index("Test", [_cafe(), _shrine()])
    assert "## Restaurants" in out
    assert "## Shrines" in out
    # Cafe section header has the count
    assert "## Restaurants (1)" in out


def test_places_index_includes_kanji_and_links() -> None:
    out = render_places_index("Test", [_cafe()])
    assert "あつた蓬莱軒 本店" in out
    assert "Tabelog" in out
    assert "https://tabelog.com/en/aichi/foo" in out


def test_places_index_marks_unmapped_places() -> None:
    out = render_places_index("Test", [_unmapped_place()])
    assert "not yet looked up" in out


# ---------- Saveable places ----------


def test_saveable_one_link_per_place() -> None:
    out = render_saveable_places("Test", [_cafe(), _shrine()])
    assert out.count("https://www.google.com/maps/search/?api=1") == 2


def test_saveable_skips_no_place_id() -> None:
    out = render_saveable_places("Test", [_unmapped_place()])
    assert "https://" not in out


def test_saveable_uses_documented_url_format() -> None:
    out = render_saveable_places("Test", [_cafe()])
    assert "query_place_id=ChIJtest_houraiken" in out


# ---------- Integration: generate() writes the full set ----------


@pytest.fixture
def populated_conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA_DDL)
    trip = TripFrontmatter(
        trip_id="t1",
        name="Test Trip",
        start_date=date(2026, 11, 15),
        end_date=date(2026, 11, 17),
        themes=["test"],
    )
    places = [
        PlaceModel(
            id="atsuta-jingu",
            name_en="Atsuta Jingu",
            name_local="熱田神宮",
            category="shrine",
            lat=35.127,
            lng=136.908,
            google_place_id="ChIJtest_jingu",
        ),
        PlaceModel(
            id="atsuta-houraiken",
            name_en="Atsuta Houraiken",
            category="restaurant",
            lat=35.120,
            lng=136.907,
            google_place_id="ChIJtest_houraiken",
        ),
    ]
    days = [
        ParsedDay(
            frontmatter=DayFrontmatter(
                day_number=1,
                date=date(2026, 11, 15),
                title="Arrival",
            ),
            place_refs=[
                DayPlaceRef("atsuta-jingu", 0),
                DayPlaceRef("atsuta-houraiken", 1),
            ],
            notes_path="trips/t1/days/day-01.md",
        ),
    ]
    sync_trip(c, trip, places, days)
    yield c
    c.close()


def test_generate_writes_all_artifacts(populated_conn: sqlite3.Connection, tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    report = generate("t1", output_dir, populated_conn)

    expected = {
        "my-maps.csv",
        "my-maps.kml",
        "daily-routes.md",
        "places-index.md",
        "saveable-places.md",
        "README.md",
    }
    actual = {p.name for p in report.files_written}
    assert actual == expected

    csv_text = (output_dir / "my-maps.csv").read_text(encoding="utf-8")
    assert "Atsuta Jingu" in csv_text
    assert "Atsuta Houraiken" in csv_text

    routes_text = (output_dir / "daily-routes.md").read_text(encoding="utf-8")
    assert "Day 1" in routes_text
    assert "place_id:ChIJtest_jingu" in routes_text

    assert report.places_total == 2
    assert report.places_pinned == 2
    assert report.places_saveable == 2


def test_generate_unknown_trip_raises(populated_conn: sqlite3.Connection, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not found"):
        generate("no-such-trip", tmp_path / "out", populated_conn)


def test_generate_updates_my_maps_generated_at(
    populated_conn: sqlite3.Connection, tmp_path: Path
) -> None:
    generate("t1", tmp_path / "out", populated_conn)
    row = populated_conn.execute("SELECT my_maps_generated_at FROM trip WHERE id = 't1'").fetchone()
    assert row[0] is not None
    # ISO-ish timestamp (date + T)
    assert "T" in row[0]


# Silence unused-import warnings for the fixtures-imported text helper
_ = textwrap
