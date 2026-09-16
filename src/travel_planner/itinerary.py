"""Conservative itinerary feasibility checks that do not invent live transit data."""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from travel_planner.db.query import DayView, PlaceView
from travel_planner.geo import distance_km

TravelMode = Literal["walking", "transit", "driving"]


def render_day_feasibility(day: DayView, travel_mode: TravelMode = "transit") -> str:
    """Render straight-line gaps and per-leg Google Maps handoffs for one day.

    It intentionally makes no duration or timetable claim. Google Maps is the
    live navigation handoff; this check only tells the planner where a day has
    implausibly large gaps before it becomes a commitment.
    """
    if travel_mode not in {"walking", "transit", "driving"}:
        raise ValueError("travel_mode must be walking, transit, or driving")
    header = f"Day {day.day_number} feasibility — {travel_mode} handoff"
    if day.date:
        header += f" · {day.date.isoformat()}"
    if day.title:
        header += f" · {day.title}"
    if len(day.links) < 2:
        return f"{header}\n\nNeed at least two planned stops to assess a leg."

    lines = [
        header,
        "",
        "Straight-line gaps only; open each link for live routing and timings.",
        "",
    ]
    for previous, current in zip(day.links[:-1], day.links[1:], strict=True):
        start, end = previous.place, current.place
        if start.lat is None or start.lng is None or end.lat is None or end.lng is None:
            lines.append(
                f"- {start.name_en} → {end.name_en}: cannot assess; missing coordinates "
                "(sync_trip looks them up)."
            )
            continue
        gap = distance_km(start.lat, start.lng, end.lat, end.lng)
        assert gap is not None
        warning = _warning(gap, travel_mode)
        lines.append(f"- {start.name_en} → {end.name_en}: {gap:.1f} km straight-line{warning}")
        lines.append(f"  {_maps_url(start, end, travel_mode)}")
    return "\n".join(lines)


def _warning(gap_km: float, travel_mode: TravelMode) -> str:
    if travel_mode == "walking" and gap_km > 2:
        return " — long for a casual walk; verify the actual route"
    if travel_mode == "transit" and gap_km > 12:
        return " — substantial transfer; verify timetable and luggage practicality"
    if travel_mode == "driving" and gap_km > 40:
        return " — substantial drive; check duration and parking"
    return ""


def _maps_url(start: PlaceView, end: PlaceView, travel_mode: TravelMode) -> str:
    assert start.lat is not None and start.lng is not None
    assert end.lat is not None and end.lng is not None
    origin = quote(f"{start.lat:.6f},{start.lng:.6f}", safe=",")
    destination = quote(f"{end.lat:.6f},{end.lng:.6f}", safe=",")
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={origin}&destination={destination}&travelmode={travel_mode}"
    )
