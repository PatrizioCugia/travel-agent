"""Saveable places generator — one Google Maps URL per place.

Tap on phone → opens Maps app on the place card → tap Save → it's in
personal saved places. The closest we get to "Save to Maps" automation
without an API (none exists).

URL format from M1-findings: `https://www.google.com/maps/search/?api=1
&query=<name>&query_place_id=<ID>`. Requires google_place_id; places
without one are skipped.
"""

from __future__ import annotations

from urllib.parse import quote

from travel_planner.db.query import PlaceView


def _maps_link(p: PlaceView) -> str | None:
    if not p.google_place_id:
        return None
    return (
        "https://www.google.com/maps/search/?api=1"
        f"&query={quote(p.name_en)}"
        f"&query_place_id={p.google_place_id}"
    )


def render_saveable_places(trip_name: str, places: list[PlaceView]) -> str:
    lines: list[str] = [
        f"# Save to Google Maps — {trip_name}",
        "",
        "Tap each link on your phone → opens in Google Maps → tap **Save** → "
        'pick a list (e.g. "Nagoya 2026"). The place is then in your '
        "personal saved places, separate from the My Maps import.",
        "",
    ]

    saveable = [p for p in places if p.google_place_id]
    if not saveable:
        lines.append("_No places have place_ids yet — run `tp parse` first._")
        lines.append("")
        return "\n".join(lines)

    by_cat: dict[str, list[PlaceView]] = {}
    for p in saveable:
        by_cat.setdefault(p.category, []).append(p)

    for cat in sorted(by_cat.keys()):
        cat_places = sorted(by_cat[cat], key=lambda p: p.name_en)
        lines.append(f"## {cat.capitalize()}s")
        lines.append("")
        for p in cat_places:
            url = _maps_link(p)
            assert url is not None  # filtered above
            sub_bits: list[str] = []
            if p.name_local:
                sub_bits.append(p.name_local)
            if p.visit_days:
                sub_bits.append(f"day(s) {', '.join(str(d) for d in p.visit_days)}")
            if p.notes:
                sub_bits.append(" ".join(p.notes.split())[:80])
            sub = " · ".join(sub_bits)
            lines.append(f"- [{p.name_en}]({url})  ")
            if sub:
                lines.append(f"  {sub}")
        lines.append("")

    return "\n".join(lines)
