"""Tests for db/sync.py — DB writes for trip + places."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import date

import pytest

from travel_planner.db.sync import sync_trip
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
