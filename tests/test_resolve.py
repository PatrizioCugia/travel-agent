"""Tests for resolve.py — fuzzy trip-slug resolution."""

from __future__ import annotations

from pathlib import Path

from travel_planner.resolve import list_trips, resolve_slug


def test_resolve_exact_match() -> None:
    slug, candidates = resolve_slug("nagoya-2026-11", ["nagoya-2026-11", "kyoto-2027-04"])
    assert slug == "nagoya-2026-11"
    assert candidates == []


def test_resolve_substring_unique() -> None:
    slug, candidates = resolve_slug("nagoya", ["nagoya-2026-11", "kyoto-2027-04"])
    assert slug == "nagoya-2026-11"
    assert candidates == []


def test_resolve_substring_ambiguous() -> None:
    slug, candidates = resolve_slug("2026", ["nagoya-2026-11", "kyoto-2026-04"])
    assert slug is None
    assert sorted(candidates) == ["kyoto-2026-04", "nagoya-2026-11"]


def test_resolve_fuzzy_match() -> None:
    # Misspelling that substring doesn't catch but partial_ratio does
    slug, candidates = resolve_slug("nagoyo", ["nagoya-2026-11", "kyoto-2027-04"])
    assert slug == "nagoya-2026-11"
    assert candidates == []


def test_resolve_no_match() -> None:
    slug, candidates = resolve_slug("paris", ["nagoya-2026-11", "kyoto-2027-04"])
    assert slug is None
    assert candidates == []


def test_resolve_empty_available() -> None:
    slug, candidates = resolve_slug("anything", [])
    assert slug is None
    assert candidates == []


def test_list_trips(tmp_path: Path) -> None:
    (tmp_path / "trip-a").mkdir()
    (tmp_path / "trip-b").mkdir()
    (tmp_path / "_template").mkdir()  # should be excluded
    (tmp_path / "not-a-dir").write_text("file, not dir", encoding="utf-8")
    trips = list_trips(tmp_path)
    assert trips == ["trip-a", "trip-b"]


def test_list_trips_missing_dir() -> None:
    assert list_trips(Path("/no/such/dir")) == []
