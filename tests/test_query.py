"""Tests for db/query.py — read-side queries returning view dataclasses."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date

import pytest

from travel_planner.db.query import load_days, load_places, load_trip
from travel_planner.db.sync import sync_trip
from travel_planner.parser.day import DayFrontmatter, DayPlaceRef, ParsedDay
from travel_planner.parser.places import PlaceModel
from travel_planner.parser.trip import TripFrontmatter
from travel_planner.schema import SCHEMA_DDL


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA_DDL)
    yield c
    c.close()


def _populate(conn: sqlite3.Connection) -> None:
    trip = TripFrontmatter(
        trip_id="t1",
        name="Test Trip",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        themes=["a", "b"],
    )
    places = [
        PlaceModel(
            id="cafe-1",
            name_en="Cafe One",
            name_local="カフェ１",
            category="cafe",
            address="1-2-3",
            lat=35.0,
            lng=135.0,
            google_place_id="ChIJ_cafe",
            tags=["test"],
            urls={"website": "https://example.com/cafe"},
            notes="A nice cafe.",
        ),
        PlaceModel(
            id="shrine-1",
            name_en="Shrine One",
            category="shrine",
            lat=35.1,
            lng=135.1,
        ),
    ]
    days = [
        ParsedDay(
            frontmatter=DayFrontmatter(
                day_number=1, date=date(2026, 1, 1), location="A", title="Arrive"
            ),
            place_refs=[DayPlaceRef("cafe-1", 0)],
            notes_path="trips/t1/days/day-01.md",
        ),
        ParsedDay(
            frontmatter=DayFrontmatter(
                day_number=2, date=date(2026, 1, 2), location="B", title="Walk"
            ),
            place_refs=[DayPlaceRef("shrine-1", 0), DayPlaceRef("cafe-1", 1)],
            notes_path="trips/t1/days/day-02.md",
        ),
    ]
    sync_trip(conn, trip, places, days)


def test_load_trip_present(conn: sqlite3.Connection) -> None:
    _populate(conn)
    t = load_trip(conn, "t1")
    assert t is not None
    assert t.name == "Test Trip"
    assert t.start_date == date(2026, 1, 1)
    assert t.themes == ["a", "b"]


def test_load_trip_missing(conn: sqlite3.Connection) -> None:
    assert load_trip(conn, "no-such-trip") is None


def test_load_places_with_visit_days(conn: sqlite3.Connection) -> None:
    _populate(conn)
    places = load_places(conn, "t1")
    assert len(places) == 2
    cafe = next(p for p in places if p.id == "cafe-1")
    assert cafe.visit_days == [1, 2]  # appears on both days
    shrine = next(p for p in places if p.id == "shrine-1")
    assert shrine.visit_days == [2]


def test_load_days_with_resolved_places(conn: sqlite3.Connection) -> None:
    _populate(conn)
    days = load_days(conn, "t1")
    assert len(days) == 2
    assert [d.day_number for d in days] == [1, 2]
    assert [link.place.id for link in days[1].links] == ["shrine-1", "cafe-1"]


def test_load_places_no_trip_returns_empty(conn: sqlite3.Connection) -> None:
    assert load_places(conn, "no-such-trip") == []
