"""Tests for maps/cache.py — JSON-backed places cache."""

from __future__ import annotations

from pathlib import Path

from travel_planner.maps.cache import PlacesCache


def test_round_trip(tmp_path: Path) -> None:
    c = PlacesCache(tmp_path / "cache.json")
    c.put("ns1", "query1", {"place_id": "abc", "lat": 1.0, "lng": 2.0})
    c.save()

    c2 = PlacesCache(tmp_path / "cache.json")
    assert c2.get("ns1", "query1") == {"place_id": "abc", "lat": 1.0, "lng": 2.0}


def test_miss_returns_none(tmp_path: Path) -> None:
    c = PlacesCache(tmp_path / "cache.json")
    assert c.get("ns", "no-such-query") is None


def test_namespace_isolation(tmp_path: Path) -> None:
    c = PlacesCache(tmp_path / "cache.json")
    c.put("ns1", "q", {"v": 1})
    c.put("ns2", "q", {"v": 2})
    assert c.get("ns1", "q") == {"v": 1}
    assert c.get("ns2", "q") == {"v": 2}


def test_corrupted_file_starts_fresh(tmp_path: Path) -> None:
    bad = tmp_path / "cache.json"
    bad.write_text("not valid json {{{", encoding="utf-8")
    c = PlacesCache(bad)
    assert c.size == 0
    # And we can still write
    c.put("ns", "q", {"ok": True})
    c.save()
    c2 = PlacesCache(bad)
    assert c2.get("ns", "q") == {"ok": True}


def test_size_property(tmp_path: Path) -> None:
    c = PlacesCache(tmp_path / "cache.json")
    assert c.size == 0
    c.put("ns", "a", {})
    c.put("ns", "b", {})
    assert c.size == 2
