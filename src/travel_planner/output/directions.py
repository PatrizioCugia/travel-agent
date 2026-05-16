"""Daily routes generator — one Google Maps directions URL per day.

Uses `place_id:<ID>` form for waypoints (avoids geocoder drift, per M1
research). Falls back to lat/lng coordinates if a place has no place_id.

Cap is 9 waypoints per URL on desktop, 3 on mobile (per Google docs). For
days exceeding the cap we split into multiple routes.
"""

from __future__ import annotations

from urllib.parse import quote

from travel_planner.db.query import DayView

WAYPOINT_CAP = 9  # desktop limit; mobile is 3, but desktop URL still loads


def _waypoint(place_id: str | None, lat: float | None, lng: float | None) -> str | None:
    if place_id:
        return f"place_id:{place_id}"
    if lat is not None and lng is not None:
        return f"{lat:.6f},{lng:.6f}"
    return None


def _build_url(waypoints: list[str], travel_mode: str = "walking") -> str:
    if not waypoints:
        return ""
    if len(waypoints) == 1:
        # `dir/?destination=...` for a single stop
        return (
            "https://www.google.com/maps/dir/?api=1"
            f"&destination={quote(waypoints[0], safe=':,')}"
            f"&travelmode={travel_mode}"
        )
    joined = "|".join(quote(w, safe=":,") for w in waypoints)
    return f"https://www.google.com/maps/dir/?api=1&waypoints={joined}&travelmode={travel_mode}"


def _routes_for_day(day: DayView) -> list[tuple[list[str], str]]:
    """Return [(stop_labels, url), ...]. Multiple entries if waypoint cap exceeded."""
    waypoints: list[tuple[str, str]] = []  # (label, waypoint_token)
    for link in day.links:
        p = link.place
        token = _waypoint(p.google_place_id, p.lat, p.lng)
        if token is None:
            continue
        waypoints.append((p.name_en, token))

    if not waypoints:
        return []

    routes: list[tuple[list[str], str]] = []
    for i in range(0, len(waypoints), WAYPOINT_CAP):
        chunk = waypoints[i : i + WAYPOINT_CAP]
        labels = [label for label, _ in chunk]
        tokens = [tok for _, tok in chunk]
        routes.append((labels, _build_url(tokens)))
    return routes


def render_daily_routes(trip_name: str, days: list[DayView]) -> str:
    """Return a markdown document with one section per day + directions URLs."""
    lines: list[str] = [f"# Daily routes — {trip_name}", ""]
    if not days:
        lines.append("_No days defined yet._")
        lines.append("")
        return "\n".join(lines)

    for day in days:
        header_bits: list[str] = [f"Day {day.day_number}"]
        if day.date:
            header_bits.append(day.date.isoformat())
        if day.location:
            header_bits.append(day.location)
        if day.title:
            header_bits.append(day.title)
        lines.append(f"## {' — '.join(header_bits)}")
        lines.append("")

        routes = _routes_for_day(day)
        if not routes:
            lines.append("_No mappable places this day._")
            lines.append("")
            continue

        for idx, (labels, url) in enumerate(routes, start=1):
            if len(routes) > 1:
                lines.append(f"### Route {idx} of {len(routes)}")
            for n, label in enumerate(labels, start=1):
                lines.append(f"{n}. {label}")
            lines.append("")
            lines.append(f"[Open in Google Maps]({url})")
            lines.append("")

    return "\n".join(lines)
