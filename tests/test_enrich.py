"""Tests for maps/enrich.py — orchestration of lookup + cache + yaml write-back."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

from travel_planner.maps.cache import PlacesCache
from travel_planner.maps.enrich import (
    enrich_places,
    write_misses_report,
)
from travel_planner.maps.places_lookup import LookupResult
from travel_planner.parser.places import load_places


def _fake_lookup(place_id: str = "ChIJ_X", confidence: float = 0.85) -> LookupResult:
    return LookupResult(
        place_id=place_id,
        lat=35.123456,
        lng=136.654321,
        name="Fake Name",
        formatted_address="Fake Address, Nagoya",
        types=["restaurant"],
        rating=4.5,
        user_ratings_total=200,
        business_status="OPERATIONAL",
        confidence=confidence,
        candidates_seen=1,
        query_used="fake query",
        language_used="ja",
    )


def _yaml(tmp_path: Path) -> Path:
    f = tmp_path / "places.yaml"
    f.write_text(
        textwrap.dedent(
            """\
            - id: p1
              name_en: Place One
              category: cafe
              address: 1-2-3 Test
            - id: p2
              name_en: Place Two
              category: shrine
              address: 4-5-6 Test
            """
        ),
        encoding="utf-8",
    )
    return f


def test_enrich_fills_missing_writes_back(tmp_path: Path) -> None:
    yaml_path = _yaml(tmp_path)
    places = load_places(yaml_path)
    cache = PlacesCache(tmp_path / "cache.json")

    with patch("travel_planner.maps.enrich.lookup_with_scoring") as mock_lookup:
        mock_lookup.side_effect = lambda *a, **k: _fake_lookup()
        report = enrich_places(places, yaml_path, cache, api_key="k")

    assert report.needed_lookup == 2
    assert report.new_matches == 2
    assert report.updates_applied == 2
    assert report.cache_hits == 0
    assert report.misses == []

    # Re-load and verify enrichment
    enriched = load_places(yaml_path)
    assert all(p.lat is not None and p.lng is not None for p in enriched)
    assert all(p.google_place_id for p in enriched)


def test_enrich_skips_already_filled(tmp_path: Path) -> None:
    yaml_path = tmp_path / "places.yaml"
    yaml_path.write_text(
        textwrap.dedent(
            """\
            - id: p1
              name_en: P1
              category: cafe
              lat: 1.0
              lng: 2.0
              google_place_id: ChIJexisting
            """
        ),
        encoding="utf-8",
    )
    places = load_places(yaml_path)
    cache = PlacesCache(tmp_path / "cache.json")

    with patch("travel_planner.maps.enrich.lookup_with_scoring") as mock_lookup:
        report = enrich_places(places, yaml_path, cache, api_key="k")

    assert mock_lookup.call_count == 0
    assert report.needed_lookup == 0


def test_enrich_force_overrides_existing(tmp_path: Path) -> None:
    yaml_path = tmp_path / "places.yaml"
    yaml_path.write_text(
        textwrap.dedent(
            """\
            - id: p1
              name_en: P1
              category: cafe
              lat: 1.0
              lng: 2.0
              google_place_id: ChIJold
            """
        ),
        encoding="utf-8",
    )
    places = load_places(yaml_path)
    cache = PlacesCache(tmp_path / "cache.json")

    with patch("travel_planner.maps.enrich.lookup_with_scoring") as mock_lookup:
        mock_lookup.return_value = _fake_lookup(place_id="ChIJnew")
        report = enrich_places(places, yaml_path, cache, api_key="k", force=True)

    assert report.new_matches == 1
    enriched = load_places(yaml_path)
    assert enriched[0].google_place_id == "ChIJnew"


def test_enrich_uses_cache_on_second_run(tmp_path: Path) -> None:
    yaml_path = _yaml(tmp_path)
    places = load_places(yaml_path)
    cache = PlacesCache(tmp_path / "cache.json")

    with patch("travel_planner.maps.enrich.lookup_with_scoring") as mock_lookup:
        mock_lookup.side_effect = lambda *a, **k: _fake_lookup()
        enrich_places(places, yaml_path, cache, api_key="k")
        first_call_count = mock_lookup.call_count

    # Re-create the cache from disk (simulate next CLI invocation), reset
    # the YAML to its pristine missing-fields state, and re-run.
    yaml_path = _yaml(tmp_path)
    places = load_places(yaml_path)
    cache2 = PlacesCache(tmp_path / "cache.json")

    with patch("travel_planner.maps.enrich.lookup_with_scoring") as mock_lookup:
        mock_lookup.side_effect = lambda *a, **k: _fake_lookup()
        report = enrich_places(places, yaml_path, cache2, api_key="k")

    assert report.cache_hits == 2
    assert report.new_matches == 0
    assert first_call_count == 2


def test_enrich_records_misses(tmp_path: Path) -> None:
    yaml_path = _yaml(tmp_path)
    places = load_places(yaml_path)
    cache = PlacesCache(tmp_path / "cache.json")

    with patch("travel_planner.maps.enrich.lookup_with_scoring") as mock_lookup:
        mock_lookup.return_value = None  # always a miss
        report = enrich_places(places, yaml_path, cache, api_key="k")

    assert len(report.misses) == 2
    assert all("no confident match" in reason for _, reason in report.misses)
    assert report.updates_applied == 0


def test_enrich_records_api_errors(tmp_path: Path) -> None:
    yaml_path = _yaml(tmp_path)
    places = load_places(yaml_path)
    cache = PlacesCache(tmp_path / "cache.json")

    with patch("travel_planner.maps.enrich.lookup_with_scoring") as mock_lookup:
        mock_lookup.side_effect = RuntimeError("boom")
        report = enrich_places(places, yaml_path, cache, api_key="k")

    assert len(report.misses) == 2
    assert all("API error" in reason for _, reason in report.misses)


def test_write_misses_report(tmp_path: Path) -> None:
    output = tmp_path / "output" / "lookup-misses.md"
    write_misses_report([("p1", "no confident match"), ("p2", "API error: X")], output)
    content = output.read_text(encoding="utf-8")
    assert "p1" in content
    assert "p2" in content
    assert "no confident match" in content
    assert content.startswith("# Lookup misses")
