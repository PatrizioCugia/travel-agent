"""Google My Maps CSV generator.

Column schema and encoding rules per M1-findings.md:
- UTF-8 **without BOM**, LF newlines, RFC-4180 quoting
- Columns: name, name_local, latitude, longitude, address, category,
           day, time_slot, description, website, tabelog_url, google_place_id
- name is Western-script (My Maps pin title); name_local is the kanji form
- Providing lat/lng + selecting them at import skips My Maps' geocoder
"""

from __future__ import annotations

import csv
import io

from travel_planner.db.query import PlaceView

COLUMNS: tuple[str, ...] = (
    "name",
    "name_local",
    "latitude",
    "longitude",
    "address",
    "category",
    "day",
    "time_slot",
    "description",
    "website",
    "tabelog_url",
    "google_place_id",
)


def _description_one_liner(notes: str | None) -> str:
    """Collapse multi-line notes to a single line for the CSV info card."""
    if not notes:
        return ""
    return " ".join(notes.split())


def render_csv(places: list[PlaceView]) -> str:
    """Return a CSV string ready to write to my-maps.csv.

    Skips places without lat/lng (can't pin) — they're still in places-index.md.
    """
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    writer.writerow(COLUMNS)
    for p in places:
        if p.lat is None or p.lng is None:
            continue
        writer.writerow(
            [
                p.name_en,
                p.name_local or "",
                f"{p.lat:.6f}",
                f"{p.lng:.6f}",
                p.address or "",
                p.category,
                ", ".join(str(d) for d in p.visit_days),
                "",  # time_slot — populated in a later milestone
                _description_one_liner(p.notes),
                p.urls.get("website", ""),
                p.urls.get("tabelog", ""),
                p.google_place_id or "",
            ]
        )
    return buf.getvalue()
