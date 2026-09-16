"""Tests for the shortlist: candidates, and promotion into places.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from travel_planner import shortlist
from travel_planner.parser.places import load_places


@pytest.fixture
def files(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "shortlist.yaml", tmp_path / "places.yaml"


def _entry(name: str = "Nishimuraya Honkan", hotel_no: int = 12345) -> dict[str, Any]:
    return shortlist.lodging_entry(
        hotel_no=hotel_no,
        name_en=name,
        name_local="西村屋本館",
        address="469 Yushima, Kinosaki-cho, Toyooka, Hyogo",
        lat=35.62, lng=134.81,
        google_place_id="ChIJtest",
        tags=["ryokan", "onsen"],
        notes="Seven public baths walkable in yukata.",
        query="城崎温泉",
        review="4.6 (312)",
        seen_price_yen=38000,
    )


def test_slugify_handles_japanese_by_falling_back() -> None:
    """A mangled slug nobody can type is worse than an honest fallback."""
    assert shortlist.slugify("Nishimuraya Honkan") == "nishimuraya-honkan"
    assert shortlist.slugify("西村屋本館", fallback="rakuten-123") == "rakuten-123"
    assert shortlist.slugify("Café  du -- Monde!") == "cafe-du-monde"


def test_add_and_load_round_trip(files: tuple[Path, Path]) -> None:
    sl, _ = files
    entry_id, added = shortlist.add("trip", _entry(), sl)
    assert entry_id == "nishimuraya-honkan"
    assert added is True

    loaded = shortlist.load("trip", sl)
    assert len(loaded) == 1
    assert loaded[0]["rakuten_hotel_no"] == 12345
    assert loaded[0]["_found"]["source"] == "rakuten"
    assert loaded[0]["_found"]["seen_price_yen"] == 38000


def test_adding_the_same_id_twice_is_a_no_op(files: tuple[Path, Path]) -> None:
    sl, _ = files
    shortlist.add("trip", _entry(), sl)
    entry_id, added = shortlist.add("trip", _entry(), sl)
    assert added is False
    assert len(shortlist.load("trip", sl)) == 1
    assert entry_id == "nishimuraya-honkan"


def test_distinct_places_with_the_same_name_get_distinct_ids(files: tuple[Path, Path]) -> None:
    sl, _ = files
    shortlist.add("trip", _entry(hotel_no=1), sl)
    second = _entry(hotel_no=2)
    second["rakuten_hotel_no"] = 2
    entry_id, added = shortlist.add("trip", second, sl)
    assert added is True
    assert entry_id == "nishimuraya-honkan-2"


def test_remove(files: tuple[Path, Path]) -> None:
    sl, _ = files
    shortlist.add("trip", _entry(), sl)
    assert shortlist.remove("trip", "nishimuraya-honkan", sl) is True
    assert shortlist.load("trip", sl) == []
    assert shortlist.remove("trip", "nishimuraya-honkan", sl) is False


def test_promote_moves_entry_and_strips_provenance(files: tuple[Path, Path]) -> None:
    sl, places = files
    shortlist.add("trip", _entry(), sl)

    promoted = shortlist.promote("trip", "nishimuraya-honkan",
                                 shortlist_path=sl, places_path=places)
    assert promoted is not None
    assert "_found" not in promoted
    assert shortlist.load("trip", sl) == []

    # And the result is a valid places.yaml the existing parser accepts.
    parsed = load_places(places)
    assert len(parsed) == 1
    assert parsed[0].id == "nishimuraya-honkan"
    assert parsed[0].rakuten_hotel_no == 12345
    assert parsed[0].category == "accommodation"


def test_promote_appends_to_an_existing_places_file(files: tuple[Path, Path]) -> None:
    sl, places = files
    places.write_text(
        "# Existing places\n"
        "- id: todaiji-nigatsudo\n"
        "  name_en: Todai-ji Nigatsudo\n"
        "  category: temple\n",
        encoding="utf-8",
    )
    shortlist.add("trip", _entry(), sl)
    shortlist.promote("trip", "nishimuraya-honkan", shortlist_path=sl, places_path=places)
    assert {p.id for p in load_places(places)} == {"todaiji-nigatsudo", "nishimuraya-honkan"}


def test_promote_unknown_id_returns_none(files: tuple[Path, Path]) -> None:
    sl, places = files
    assert shortlist.promote("trip", "nope", shortlist_path=sl, places_path=places) is None


def test_promote_conflict_explains_what_to_do(files: tuple[Path, Path]) -> None:
    sl, places = files
    shortlist.add("trip", _entry(), sl)
    places.write_text(
        "- id: nishimuraya-honkan\n  name_en: Already here\n  category: accommodation\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"already in places\.yaml"):
        shortlist.promote("trip", "nishimuraya-honkan", shortlist_path=sl, places_path=places)


def test_food_entry_shape(files: tuple[Path, Path]) -> None:
    sl, _ = files
    entry = shortlist.food_entry(
        name="Nakatanidou", name_local="中谷堂", address="29 Hashimotocho, Nara",
        google_place_id="ChIJmochi", tags=["mochi", "booking-needed"],
        query="mochi near Todai-ji", review="4.3 (1200)",
    )
    entry_id, added = shortlist.add("trip", entry, sl)
    assert (entry_id, added) == ("nakatanidou", True)
    loaded = shortlist.load("trip", sl)[0]
    assert loaded["category"] == "restaurant"
    assert loaded["name_local"] == "中谷堂"
    assert loaded["_found"]["source"] == "google-places"


def test_activity_entry_preserves_source_ref_when_promoted(files: tuple[Path, Path]) -> None:
    sl, places = files
    entry = shortlist.activity_entry(
        source="openstreetmap",
        source_id="node/456",
        source_url="https://www.openstreetmap.org/node/456",
        name="Shirahama Onsen",
        name_local="白浜温泉",
        category="onsen",
        address="Shirahama, Wakayama",
        lat=33.678,
        lng=135.348,
        tags=["amenity:public_bath"],
    )
    entry_id, added = shortlist.add("trip", entry, sl)
    assert (entry_id, added) == ("shirahama-onsen", True)

    promoted = shortlist.promote("trip", entry_id, shortlist_path=sl, places_path=places)
    assert promoted is not None
    assert promoted["source_refs"] == {"openstreetmap": "node/456"}
    assert "_found" not in promoted
    parsed = load_places(places)
    assert parsed[0].source_refs == {"openstreetmap": "node/456"}


def test_render_empty_and_populated(files: tuple[Path, Path]) -> None:
    sl, _ = files
    assert shortlist.render([]) == "Shortlist is empty."
    shortlist.add("trip", _entry(), sl)
    text = shortlist.render(shortlist.load("trip", sl))
    assert "accommodation (1)" in text
    assert "nishimuraya-honkan" in text
    assert "rakuten #12345" in text


def test_header_survives_every_save(files: tuple[Path, Path]) -> None:
    sl, _ = files
    for n in range(3):
        shortlist.add("trip", _entry(f"Inn {n}", hotel_no=n), sl)
        assert sl.read_text(encoding="utf-8").count(shortlist.SHORTLIST_HEADER) == 1
    assert len(shortlist.load("trip", sl)) == 3


def test_malformed_shortlist_raises_value_error_naming_the_file(
    files: tuple[Path, Path],
) -> None:
    sl, _ = files
    sl.write_text("- id: x\n  name_en: [unclosed\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"shortlist\.yaml is not valid YAML"):
        shortlist.load("trip", sl)


def test_promote_refuses_the_same_inn_under_another_id(files: tuple[Path, Path]) -> None:
    sl, places = files
    shortlist.add("trip", _entry(), sl)
    places.write_text(
        "- id: nishimuraya\n  name_en: Nishimuraya\n  category: accommodation\n"
        "  rakuten_hotel_no: 12345\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"as 'nishimuraya' \(same rakuten_hotel_no\)"):
        shortlist.promote("trip", "nishimuraya-honkan", shortlist_path=sl, places_path=places)
    assert len(shortlist.load("trip", sl)) == 1                  # nothing moved
