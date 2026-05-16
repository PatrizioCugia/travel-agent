"""Read-side queries for trip + places + days.

Returns dataclass "view" objects rather than tuples so output generators
have a clear, typed interface. These views are read-only snapshots from
the DB; mutating one doesn't propagate back.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date as date_t


@dataclass
class TripView:
    id: str
    name: str
    start_date: date_t | None
    end_date: date_t | None
    total_budget_kr: int | None
    themes: list[str] = field(default_factory=list)
    notes_path: str | None = None
    my_maps_url: str | None = None


@dataclass
class PlaceView:
    id: str
    name_en: str
    name_local: str | None
    category: str
    address: str | None
    lat: float | None
    lng: float | None
    google_place_id: str | None
    tags: list[str] = field(default_factory=list)
    urls: dict[str, str] = field(default_factory=dict)
    notes: str | None = None
    visit_days: list[int] = field(default_factory=list)  # day_numbers


@dataclass
class DayPlaceLink:
    place: PlaceView
    order_in_day: int
    time_slot: str | None
    notes: str | None


@dataclass
class DayView:
    day_number: int
    date: date_t | None
    location: str | None
    title: str | None
    notes_path: str | None
    links: list[DayPlaceLink] = field(default_factory=list)


def _parse_date(s: str | None) -> date_t | None:
    return date_t.fromisoformat(s) if s else None


def load_trip(conn: sqlite3.Connection, trip_id: str) -> TripView | None:
    """Fetch the trip row by id, or None if missing."""
    row = conn.execute(
        """
        SELECT id, name, start_date, end_date, total_budget_kr,
               themes_json, notes_path, my_maps_url
        FROM trip WHERE id = ?
        """,
        (trip_id,),
    ).fetchone()
    if row is None:
        return None
    return TripView(
        id=row[0],
        name=row[1],
        start_date=_parse_date(row[2]),
        end_date=_parse_date(row[3]),
        total_budget_kr=row[4],
        themes=json.loads(row[5]) if row[5] else [],
        notes_path=row[6],
        my_maps_url=row[7],
    )


def load_places(conn: sqlite3.Connection, trip_id: str) -> list[PlaceView]:
    """Fetch all places for a trip, with visit_days populated from day_place."""
    rows = conn.execute(
        """
        SELECT id, name_en, name_local, category, address,
               lat, lng, google_place_id, tags_json, urls_json, notes
        FROM place WHERE trip_id = ? ORDER BY id
        """,
        (trip_id,),
    ).fetchall()

    places: dict[str, PlaceView] = {}
    for r in rows:
        p = PlaceView(
            id=r[0],
            name_en=r[1],
            name_local=r[2],
            category=r[3],
            address=r[4],
            lat=r[5],
            lng=r[6],
            google_place_id=r[7],
            tags=json.loads(r[8]) if r[8] else [],
            urls=json.loads(r[9]) if r[9] else {},
            notes=r[10],
        )
        places[p.id] = p

    visit_rows = conn.execute(
        """
        SELECT dp.place_id, d.day_number
        FROM day_place dp JOIN day d ON d.id = dp.day_id
        WHERE dp.trip_id = ?
        ORDER BY d.day_number, dp.order_in_day
        """,
        (trip_id,),
    ).fetchall()
    for place_id, day_number in visit_rows:
        if place_id in places and day_number not in places[place_id].visit_days:
            places[place_id].visit_days.append(day_number)

    return sorted(places.values(), key=lambda p: p.id)


def load_days(conn: sqlite3.Connection, trip_id: str) -> list[DayView]:
    """Fetch all days for a trip, with their place links resolved."""
    places_by_id = {p.id: p for p in load_places(conn, trip_id)}

    day_rows = conn.execute(
        """
        SELECT id, day_number, date, location, title, notes_path
        FROM day WHERE trip_id = ? ORDER BY day_number
        """,
        (trip_id,),
    ).fetchall()

    days: list[DayView] = []
    for d_id, day_number, d_date, location, title, notes_path in day_rows:
        link_rows = conn.execute(
            """
            SELECT place_id, order_in_day, time_slot, notes
            FROM day_place WHERE day_id = ? ORDER BY order_in_day
            """,
            (d_id,),
        ).fetchall()
        links: list[DayPlaceLink] = []
        for place_id, order_in_day, time_slot, dp_notes in link_rows:
            place = places_by_id.get(place_id)
            if place is None:
                continue
            links.append(
                DayPlaceLink(
                    place=place,
                    order_in_day=order_in_day,
                    time_slot=time_slot,
                    notes=dp_notes,
                )
            )
        days.append(
            DayView(
                day_number=day_number,
                date=_parse_date(d_date),
                location=location,
                title=title,
                notes_path=notes_path,
                links=links,
            )
        )

    return days
