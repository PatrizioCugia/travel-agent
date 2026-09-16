"""Tests for bounded, normalized OSM discovery responses."""

from __future__ import annotations

from pathlib import Path

from travel_planner.discovery.cache import DiscoveryCache
from travel_planner.discovery.models import DiscoveryCandidate
from travel_planner.discovery.osm import build_query, search_nearby


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


class _Client:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.query = ""

    def post(
        self,
        _url: str,
        *,
        data: dict[str, str],
        headers: dict[str, str],
        timeout: float,
    ) -> _Response:
        del headers, timeout
        self.query = data["data"]
        return _Response(self.payload)


def test_build_query_is_bounded_and_kind_specific() -> None:
    query = build_query("onsen", 35.0, 135.0, 4000)
    assert "around:4000,35.000000,135.000000" in query
    assert '"amenity"="public_bath"' in query
    assert '"natural"="hot_spring"' in query

    traditional_query = build_query("traditional_inn", 35.0, 135.0, 4000)
    assert '"tourism"~"guest_house|hotel"]["name"~"民宿|宿坊"' in traditional_query
    assert '"amenity"="place_of_worship"]["name:ja"~"宿坊"' in traditional_query


def test_search_normalizes_nodes_and_ways_then_sorts_by_distance() -> None:
    client = _Client(
        {
            "elements": [
                {
                    "type": "way",
                    "id": 2,
                    "center": {"lat": 35.03, "lon": 135.03},
                    "tags": {"name": "Far Bath", "amenity": "public_bath"},
                },
                {
                    "type": "node",
                    "id": 1,
                    "lat": 35.001,
                    "lon": 135.001,
                    "tags": {
                        "name": "近い温泉",
                        "name:en": "Near Onsen",
                        "name:ja": "近い温泉",
                        "amenity": "public_bath",
                        "onsen": "yes",
                        "opening_hours": "10:00-21:00",
                        "website": "https://example.test/onsen",
                        "addr:city": "Test City",
                    },
                },
                {"type": "node", "id": 3, "lat": 35.0, "lon": 135.0, "tags": {}},
            ]
        }
    )

    candidates = search_nearby("onsen", lat=35.0, lng=135.0, client=client)

    assert [candidate.source_id for candidate in candidates] == ["node/1", "way/2"]
    first = candidates[0]
    assert first.name == "Near Onsen"
    assert first.name_local == "近い温泉"
    assert first.category == "onsen"
    assert first.address == "Test City"
    assert first.website == "https://example.test/onsen"
    assert first.opening_hours == "10:00-21:00"
    assert first.tags == ["onsen:yes", "amenity:public_bath"]
    assert "out center tags" in client.query


def test_traditional_inn_requires_an_explicit_minshuku_or_temple_lodging_name() -> None:
    client = _Client(
        {
            "elements": [
                {
                    "type": "node",
                    "id": 42,
                    "lat": 35.001,
                    "lon": 135.001,
                    "tags": {
                        "name": "民宿 山の家",
                        "name:en": "Yama no Ie",
                        "tourism": "guest_house",
                    },
                }
            ]
        }
    )

    candidates = search_nearby("traditional_inn", lat=35.0, lng=135.0, client=client)

    assert len(candidates) == 1
    assert candidates[0].name == "Yama no Ie"
    assert candidates[0].category == "minshuku"
    assert candidates[0].tags == ["tourism:guest_house", "lodging-style:minshuku"]


def test_cache_round_trips_normalized_candidate(tmp_path: Path) -> None:
    candidate = DiscoveryCandidate(
        source="openstreetmap",
        source_id="node/9",
        source_url="https://www.openstreetmap.org/node/9",
        licence="OpenStreetMap contributors, ODbL 1.0",
        name="Test Bath",
        category="onsen",
        lat=35.0,
        lng=135.0,
    )
    path = tmp_path / "candidates.json"
    DiscoveryCache(path).put_many([candidate])

    loaded = DiscoveryCache(path).get("openstreetmap:node/9")
    assert loaded == candidate
