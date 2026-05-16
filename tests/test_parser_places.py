"""Tests for parser/places.py — places.yaml loading + validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from travel_planner.parser.places import PlaceModel, load_places

FIXTURE = Path(__file__).parent / "fixtures" / "trips" / "test-trip-01"


def test_load_places_validates_fixture() -> None:
    places = load_places(FIXTURE / "places.yaml")
    assert len(places) == 2

    cafe = places[0]
    assert cafe.id == "test-cafe-1"
    assert cafe.name_en == "Test Cafe One"
    assert cafe.category == "cafe"
    assert cafe.lat == 35.0
    assert cafe.lng == 135.0
    assert cafe.tags == ["test", "fixture"]
    assert cafe.urls == {"website": "https://example.com/cafe-1"}
    assert cafe.notes == "A test cafe."

    shrine = places[1]
    assert shrine.id == "test-shrine-1"
    assert shrine.name_local == "テスト神社"
    assert shrine.category == "shrine"
    assert shrine.lat is None  # not yet looked up


def test_invalid_category_rejected() -> None:
    with pytest.raises(ValidationError, match="category"):
        PlaceModel.model_validate(
            {"id": "bad", "name_en": "Bad", "category": "not-a-real-category"}
        )


def test_invalid_slug_rejected() -> None:
    with pytest.raises(ValidationError, match="kebab-case"):
        PlaceModel.model_validate({"id": "Bad_Slug", "name_en": "X", "category": "cafe"})


def test_slug_with_double_hyphen_rejected() -> None:
    with pytest.raises(ValidationError, match="kebab-case"):
        PlaceModel.model_validate({"id": "double--hyphen", "name_en": "X", "category": "cafe"})


def test_empty_file_returns_empty_list(tmp_path: Path) -> None:
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    assert load_places(empty) == []


def test_non_list_yaml_rejected(tmp_path: Path) -> None:
    not_a_list = tmp_path / "bad.yaml"
    not_a_list.write_text("key: value\n", encoding="utf-8")
    with pytest.raises(ValueError, match="list at top level"):
        load_places(not_a_list)


def test_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_places(Path("/nonexistent/places.yaml"))
