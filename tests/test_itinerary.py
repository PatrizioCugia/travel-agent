"""Tests for conservative route-feasibility output."""

from __future__ import annotations

from travel_planner.db.query import DayPlaceLink, DayView, PlaceView
from travel_planner.itinerary import render_day_feasibility


def _place(name: str, lat: float | None, lng: float | None) -> PlaceView:
    return PlaceView(
        id=name.lower().replace(" ", "-"),
        name_en=name,
        name_local=None,
        category="sight",
        address=None,
        lat=lat,
        lng=lng,
        google_place_id=None,
    )


def test_feasibility_outputs_live_maps_handoff_and_walk_warning() -> None:
    day = DayView(
        day_number=3,
        date=None,
        location=None,
        title="Long walk",
        notes_path=None,
        links=[
            DayPlaceLink(
                place=_place("Start", 35.0, 135.0), order_in_day=0, time_slot=None, notes=None
            ),
            DayPlaceLink(
                place=_place("End", 35.03, 135.0), order_in_day=1, time_slot=None, notes=None
            ),
        ],
    )
    output = render_day_feasibility(day, "walking")
    assert "straight-line" in output
    assert "long for a casual walk" in output
    assert "travelmode=walking" in output


def test_feasibility_reports_missing_coordinates_without_link() -> None:
    day = DayView(
        day_number=1,
        date=None,
        location=None,
        title=None,
        notes_path=None,
        links=[
            DayPlaceLink(
                place=_place("Start", 35.0, 135.0), order_in_day=0, time_slot=None, notes=None
            ),
            DayPlaceLink(
                place=_place("Unknown", None, None), order_in_day=1, time_slot=None, notes=None
            ),
        ],
    )
    output = render_day_feasibility(day)
    assert "cannot assess; missing coordinates" in output
    assert "google.com/maps" not in output
