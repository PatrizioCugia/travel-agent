"""Tests for output formatting and the restaurant heuristics."""

from __future__ import annotations

from typing import Any

import pytest

from travel_planner import format as fmt
from travel_planner.food.search import FoodHit


def _hit(**kwargs: object) -> FoodHit:
    base: dict[str, Any] = dict(
        place_id="x", name="Test", address="Nara", lat=None, lng=None,
        rating=None, rating_count=None, price_level=None, kind=None, types=[],
    )
    base.update(kwargs)
    return FoodHit(**base)


def test_yen_formatting() -> None:
    assert fmt.yen(38000) == "¥38,000"
    assert fmt.yen(None) == "price n/a"


def test_kroner_conversion_needs_a_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JPY_PER_DKK", raising=False)
    assert fmt.yen_kr(24800) == "¥24,800"
    monkeypatch.setenv("JPY_PER_DKK", "24.8")
    assert fmt.yen_kr(24800) == "¥24,800 (~1,000 kr)"


def test_a_broken_rate_degrades_to_yen(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo in .env should cost you the conversion, not the search."""
    monkeypatch.setenv("JPY_PER_DKK", "not-a-number")
    assert fmt.yen_kr(24800) == "¥24,800"
    monkeypatch.setenv("JPY_PER_DKK", "0")
    assert fmt.yen_kr(24800) == "¥24,800"


def test_meals() -> None:
    assert fmt.meals(True, True) == "夕朝"
    assert fmt.meals(True, False) == "夕"
    assert fmt.meals(False, False) == ""
    assert fmt.meals_en(True, True) == "half board"
    assert fmt.meals_en(False, False) == "room only"


def test_review_handles_count_without_average() -> None:
    """Rakuten returns a count and no average for barely-reviewed places."""
    assert fmt.review(4.08, 508) == "4.08 (508)"
    assert fmt.review(None, 3) == "3 review(s), unrated"
    assert fmt.review(None, 0) == "no reviews"


def test_name_line_puts_western_script_first() -> None:
    assert fmt.name_line("Nishimuraya", "西村屋") == "Nishimuraya 西村屋"
    assert fmt.name_line(None, "西村屋") == "西村屋"
    assert fmt.name_line("Nishimuraya", None) == "Nishimuraya"


def test_booking_likely_flags_expensive_places() -> None:
    assert _hit(price_level="PRICE_LEVEL_VERY_EXPENSIVE").booking_likely is True
    assert _hit(price_level="PRICE_LEVEL_MODERATE").booking_likely is False


def test_booking_likely_flags_good_sushi_counters() -> None:
    assert _hit(types=["sushi_restaurant"], rating=4.6).booking_likely is True
    assert _hit(types=["sushi_restaurant"], rating=3.8).booking_likely is False
    assert _hit(types=["ramen_restaurant"], rating=4.9).booking_likely is False


def test_closed_days_parsed_from_google_hours() -> None:
    hit = _hit(weekday_hours=[
        "Monday: 11:00-14:00", "Tuesday: Closed", "Wednesday: Closed",
        "Thursday: 11:00-14:00",
    ])
    assert hit.closed_days == ["Tue", "Wed"]
    assert _hit().closed_days == []


def test_tabelog_link_is_a_search_url_not_a_scrape() -> None:
    assert _hit(name="中谷堂").tabelog_url().startswith("https://tabelog.com/en/rstLst/?sk=")


def test_results_are_gated_to_twice_the_requested_radius(monkeypatch: pytest.MonkeyPatch) -> None:
    """Places' locationBias is a hint: a Nara search returns Osaka results."""
    from travel_planner.food import search as food_mod
    from travel_planner.geo import Location

    centre = Location(name="Tōdai-ji", address="Nara", lat=34.689, lng=135.840, place_id="x")
    monkeypatch.setattr(food_mod, "geocode", lambda *a, **k: centre)
    monkeypatch.setattr(food_mod, "api_key", lambda *a, **k: "fake")

    near = {"id": "near", "displayName": {"text": "Nara place"},
            "location": {"latitude": 34.690, "longitude": 135.841}}
    far = {"id": "far", "displayName": {"text": "Osaka place"},
           "location": {"latitude": 34.703, "longitude": 135.512}}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"places": [far, near]}

    monkeypatch.setattr("travel_planner.food.search.requests.post",
                        lambda *a, **k: FakeResponse())
    _, hits = food_mod.search_food("Todai-ji Nara", radius_m=1200)
    assert [h.name for h in hits] == ["Nara place"]


def test_http_logging_is_silenced_so_api_keys_never_reach_logs() -> None:
    """Rakuten auth rides in the query string; httpx logs URLs at INFO."""
    import logging

    from travel_planner.logging_setup import NOISY_LOGGERS, quiet_http_logging

    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.DEBUG)
    quiet_http_logging()
    assert all(logging.getLogger(n).level >= logging.WARNING for n in NOISY_LOGGERS)


def test_food_line_carries_the_place_id() -> None:
    """Without it, a result can't be shortlisted without searching again."""
    assert "ChIJtest123" in _hit(place_id="ChIJtest123").line()
