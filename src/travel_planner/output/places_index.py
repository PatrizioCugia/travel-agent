"""Places index generator — all places grouped by category.

Human-readable reference markdown; not consumed by My Maps. Useful for
Patrizio scanning the full place list (and useful for Claude to read when
answering "what restaurants are in Nagoya?").
"""

from __future__ import annotations

from travel_planner.db.query import PlaceView

# Display order for categories. Anything not listed falls to the end,
# alphabetically.
_CATEGORY_ORDER: tuple[str, ...] = (
    "restaurant",
    "cafe",
    "bar",
    "accommodation",
    "shrine",
    "temple",
    "sight",
    "garden",
    "museum",
    "viewpoint",
    "market",
    "shop",
    "onsen",
    "ropeway",
    "transit",
)


def _sort_key(category: str) -> tuple[int, str]:
    try:
        return (_CATEGORY_ORDER.index(category), category)
    except ValueError:
        return (len(_CATEGORY_ORDER), category)


def _group_by_category(places: list[PlaceView]) -> dict[str, list[PlaceView]]:
    by_cat: dict[str, list[PlaceView]] = {}
    for p in places:
        by_cat.setdefault(p.category, []).append(p)
    return by_cat


def _render_place(p: PlaceView) -> list[str]:
    lines: list[str] = []
    title = p.name_en
    if p.name_local:
        title += f" · {p.name_local}"
    lines.append(f"### {title}")
    if p.address:
        lines.append(f"- **Address**: {p.address}")
    if p.visit_days:
        lines.append(f"- **Day(s)**: {', '.join(str(d) for d in p.visit_days)}")
    if p.tags:
        lines.append(f"- **Tags**: {', '.join(p.tags)}")
    for label, url in p.urls.items():
        lines.append(f"- **{label.title()}**: <{url}>")
    if p.lat is not None and p.lng is not None:
        lines.append(f"- **Coords**: {p.lat:.6f}, {p.lng:.6f}")
    else:
        lines.append("- **Coords**: _not yet looked up_")
    if p.google_place_id:
        lines.append(f"- **place_id**: `{p.google_place_id}`")
    if p.notes:
        lines.append("")
        lines.append(p.notes.strip())
    lines.append("")
    return lines


def render_places_index(trip_name: str, places: list[PlaceView]) -> str:
    lines: list[str] = [f"# Places index — {trip_name}", ""]
    if not places:
        lines.append("_No places defined yet._")
        lines.append("")
        return "\n".join(lines)

    by_cat = _group_by_category(places)
    for cat in sorted(by_cat.keys(), key=_sort_key):
        cat_places = sorted(by_cat[cat], key=lambda p: p.name_en)
        lines.append(f"## {cat.capitalize()}s ({len(cat_places)})")
        lines.append("")
        for p in cat_places:
            lines.extend(_render_place(p))

    return "\n".join(lines)
