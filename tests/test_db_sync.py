"""Tests for db/sync.py — DB writes for trip + places + days."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import date

import pytest

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


def _trip() -> TripFrontmatter:
    return TripFrontmatter(
        trip_id="t1",
        name="Test",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        total_budget_kr=10000,
        themes=["a", "b"],
    )


def _places() -> list[PlaceModel]:
    return [
        PlaceModel(
            id="p1",
            name_en="P One",
            category="cafe",
            tags=["test"],
            urls={"website": "https://example.com"},
        ),
        PlaceModel(id="p2", name_en="P Two", category="shrine"),
    ]


def test_sync_writes_trip_and_places(conn: sqlite3.Connection) -> None:
    sync_trip(conn, _trip(), _places())

    trips = conn.execute(
        "SELECT id, name, start_date, end_date, total_budget_kr, themes_json FROM trip"
    ).fetchall()
    assert trips == [("t1", "Test", "2026-01-01", "2026-01-03", 10000, '["a", "b"]')]

    places = conn.execute(
        "SELECT id, trip_id, name_en, category, tags_json, urls_json FROM place ORDER BY id"
    ).fetchall()
    assert places == [
        ("p1", "t1", "P One", "cafe", '["test"]', '{"website": "https://example.com"}'),
        ("p2", "t1", "P Two", "shrine", "[]", "{}"),
    ]


def test_sync_is_idempotent(conn: sqlite3.Connection) -> None:
    sync_trip(conn, _trip(), _places())
    sync_trip(conn, _trip(), _places())  # second call must not duplicate
    count = conn.execute("SELECT COUNT(*) FROM place").fetchone()[0]
    assert count == 2


def test_sync_removes_dropped_places_on_resync(conn: sqlite3.Connection) -> None:
    sync_trip(conn, _trip(), _places())
    # Re-sync with only one place — the other should disappear (cascade delete)
    sync_trip(conn, _trip(), [_places()[0]])
    places = conn.execute("SELECT id FROM place").fetchall()
    assert places == [("p1",)]


def test_sync_handles_tbd_dates(conn: sqlite3.Connection) -> None:
    trip = TripFrontmatter(trip_id="t1", name="TBD")
    sync_trip(conn, trip, [])
    row = conn.execute("SELECT start_date, end_date FROM trip").fetchone()
    assert row == (None, None)


def test_themes_round_trip_as_json(conn: sqlite3.Connection) -> None:
    sync_trip(conn, _trip(), [])
    themes_json = conn.execute("SELECT themes_json FROM trip").fetchone()[0]
    assert json.loads(themes_json) == ["a", "b"]


def _days() -> list[ParsedDay]:
    return [
        ParsedDay(
            frontmatter=DayFrontmatter(
                day_number=1, date=date(2026, 1, 1), location="A", title="Arrive"
            ),
            place_refs=[DayPlaceRef(place_slug="p1", order_in_day=0)],
            notes_path="trips/t1/days/day-01.md",
        ),
        ParsedDay(
            frontmatter=DayFrontmatter(
                day_number=2, date=date(2026, 1, 2), location="B", title="Walk"
            ),
            place_refs=[
                DayPlaceRef(place_slug="p2", order_in_day=0),
                DayPlaceRef(place_slug="p1", order_in_day=1),
            ],
            notes_path="trips/t1/days/day-02.md",
        ),
    ]


def test_sync_writes_days_and_day_places(conn: sqlite3.Connection) -> None:
    sync_trip(conn, _trip(), _places(), _days())

    days = conn.execute(
        "SELECT trip_id, day_number, date, location, title FROM day ORDER BY day_number"
    ).fetchall()
    assert days == [
        ("t1", 1, "2026-01-01", "A", "Arrive"),
        ("t1", 2, "2026-01-02", "B", "Walk"),
    ]

    dps = conn.execute(
        """
        SELECT d.day_number, dp.place_id, dp.order_in_day
        FROM day_place dp
        JOIN day d ON d.id = dp.day_id
        ORDER BY d.day_number, dp.order_in_day
        """
    ).fetchall()
    assert dps == [(1, "p1", 0), (2, "p2", 0), (2, "p1", 1)]


def test_sync_resync_clears_days(conn: sqlite3.Connection) -> None:
    sync_trip(conn, _trip(), _places(), _days())
    sync_trip(conn, _trip(), _places(), [])  # remove all days
    assert conn.execute("SELECT COUNT(*) FROM day").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM day_place").fetchone()[0] == 0


def test_sync_without_days_argument(conn: sqlite3.Connection) -> None:
    """Backwards-compatible call: days defaults to empty."""
    sync_trip(conn, _trip(), _places())
    assert conn.execute("SELECT COUNT(*) FROM day").fetchone()[0] == 0
