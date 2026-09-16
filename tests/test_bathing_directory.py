"""Tests for reviewed Japanese operator/destination bathing directories."""

from __future__ import annotations

from travel_planner import mcp_server
from travel_planner.discovery import bathing_directory


def test_japanese_area_name_returns_the_reviewed_kinosaki_directory() -> None:
    match = bathing_directory.find("城崎温泉")
    assert match is not None
    directory, selected = match
    assert selected is None
    assert directory.authority == "城崎温泉観光協会"
    assert len(directory.members) == 7


def test_directory_separates_published_schedule_from_temporary_closure() -> None:
    match = bathing_directory.find("さとの湯")
    assert match is not None
    _, member = match
    assert member is not None
    assert member.day_use_status == "temporarily_closed"
    assert "2024-03-31" in member.status_detail


def test_render_uses_japanese_member_names_and_does_not_overstate_opening() -> None:
    text = bathing_directory.render("城崎温泉")
    assert text is not None
    assert "地蔵湯 / Jizo-yu" in text
    assert "さとの湯 / Satono-yu — temporarily closed" in text
    assert "not a real-time open signal" in text


def test_unknown_area_is_not_fuzzy_matched() -> None:
    assert bathing_directory.render("城崎") is None


def test_onsen_discovery_prefers_the_official_japanese_directory_before_osm() -> None:
    text = mcp_server.discover_nearby("城崎温泉", "onsen")
    assert "official Japanese public-bath directory" in text
    assert "城崎温泉観光協会" in text
    assert "OpenStreetMap" not in text
