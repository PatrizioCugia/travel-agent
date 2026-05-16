"""Tests for parser/trip.py — trip.md frontmatter loading + validation."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from travel_planner.parser.trip import (
    load_trip_frontmatter,
    split_frontmatter,
)

FIXTURE = Path(__file__).parent / "fixtures" / "trips" / "test-trip-01"


def test_split_frontmatter_extracts_yaml() -> None:
    yaml, body = split_frontmatter("---\nkey: value\n---\n\nBody here.\n")
    assert yaml == "key: value"
    assert body == "\nBody here.\n"


def test_split_frontmatter_handles_missing_frontmatter() -> None:
    yaml, body = split_frontmatter("Just body, no frontmatter.\n")
    assert yaml == ""
    assert body == "Just body, no frontmatter.\n"


def test_split_frontmatter_malformed_raises() -> None:
    with pytest.raises(ValueError, match="malformed"):
        split_frontmatter("---\nkey: value\n(missing closing delim)\n")


def test_load_trip_frontmatter_fixture() -> None:
    trip = load_trip_frontmatter(FIXTURE / "trip.md")
    assert trip.trip_id == "test-trip-01"
    assert trip.name == "Test Trip"
    assert trip.start_date == date(2026, 1, 1)
    assert trip.end_date == date(2026, 1, 3)
    assert trip.total_budget_kr == 10_000
    assert trip.themes == ["test", "fixture"]


def test_load_trip_frontmatter_tbd_dates(tmp_path: Path) -> None:
    f = tmp_path / "trip.md"
    f.write_text(
        "---\ntrip_id: tbd\nname: TBD Trip\n---\n\nNo dates yet.\n",
        encoding="utf-8",
    )
    trip = load_trip_frontmatter(f)
    assert trip.start_date is None
    assert trip.end_date is None
    assert trip.themes == []


def test_load_trip_frontmatter_no_frontmatter_raises(tmp_path: Path) -> None:
    f = tmp_path / "trip.md"
    f.write_text("No frontmatter at all.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no frontmatter"):
        load_trip_frontmatter(f)
