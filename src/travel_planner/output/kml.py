"""KML generator — alternative to CSV with per-category styling baked in.

KML lets us declare `<Style>` blocks per category up front and reference
them per-placemark, so a fresh import to My Maps comes with icon colors
already correct (no "Style by data column" click needed).
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from travel_planner.db.query import PlaceView

# Google's free paddle icons. One color per category; categories not in
# this map fall back to "gray-blank".
_ICON_COLOR_BY_CATEGORY: dict[str, str] = {
    "restaurant": "red",
    "bar": "pink",
    "cafe": "orange",
    "accommodation": "blue",
    "sight": "green",
    "viewpoint": "green",
    "garden": "grn",  # google uses 3-letter abbrev for one variant
    "museum": "ltblu",
    "shrine": "purple",
    "temple": "purple",
    "market": "ylw",
    "shop": "ylw",
    "transit": "wht",
    "onsen": "blu",
    "ropeway": "blu",
}


def _icon_href(color: str) -> str:
    return f"http://maps.google.com/mapfiles/kml/paddle/{color}-circle.png"


def _style_id(category: str) -> str:
    return f"cat-{category}"


def _categories_in(places: list[PlaceView]) -> list[str]:
    seen: set[str] = set()
    order: list[str] = []
    for p in places:
        if p.category not in seen:
            seen.add(p.category)
            order.append(p.category)
    return order


def _styles_block(places: list[PlaceView]) -> str:
    lines: list[str] = []
    for cat in _categories_in(places):
        color = _ICON_COLOR_BY_CATEGORY.get(cat, "wht")
        lines.append(f'    <Style id="{_style_id(cat)}">')
        lines.append("      <IconStyle>")
        lines.append(f"        <Icon><href>{_icon_href(color)}</href></Icon>")
        lines.append("      </IconStyle>")
        lines.append("    </Style>")
    return "\n".join(lines)


def _description_html(p: PlaceView) -> str:
    parts: list[str] = []
    if p.name_local:
        parts.append(f"<p><b>{escape(p.name_local)}</b></p>")
    if p.address:
        parts.append(f"<p>{escape(p.address)}</p>")
    if p.visit_days:
        parts.append(f"<p>Day(s): {', '.join(str(d) for d in p.visit_days)}</p>")
    if p.notes:
        parts.append(f"<p>{escape(' '.join(p.notes.split()))}</p>")
    if p.urls:
        for label, url in p.urls.items():
            parts.append(f'<p><a href="{escape(url)}">{escape(label.title())}</a></p>')
    return "".join(parts)


def _placemark(p: PlaceView) -> str:
    assert p.lat is not None and p.lng is not None  # filtered upstream
    return (
        "    <Placemark>\n"
        f"      <name>{escape(p.name_en)}</name>\n"
        f"      <styleUrl>#{_style_id(p.category)}</styleUrl>\n"
        f"      <description><![CDATA[{_description_html(p)}]]></description>\n"
        "      <Point>\n"
        f"        <coordinates>{p.lng:.6f},{p.lat:.6f}</coordinates>\n"
        "      </Point>\n"
        "    </Placemark>"
    )


def render_kml(map_name: str, places: list[PlaceView]) -> str:
    """Return a KML document string. Skips places without lat/lng."""
    pinned = [p for p in places if p.lat is not None and p.lng is not None]
    placemarks = "\n".join(_placemark(p) for p in pinned)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
        "  <Document>\n"
        f"    <name>{escape(map_name)}</name>\n"
        f"{_styles_block(pinned)}\n"
        f"{placemarks}\n"
        "  </Document>\n"
        "</kml>\n"
    )
