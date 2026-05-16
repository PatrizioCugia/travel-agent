"""SQLite sync for parsed trip + places + days.

Idempotent: DELETE-then-INSERT scoped to one trip_id. Re-running `tp parse`
on the same trip is safe and produces the same DB state.
"""

from __future__ import annotations

import json
import sqlite3

from travel_planner.parser.day import ParsedDay
from travel_planner.parser.places import PlaceModel
from travel_planner.parser.trip import TripFrontmatter
from travel_planner.schema import SCHEMA_DDL


def sync_trip(
    conn: sqlite3.Connection,
    trip: TripFrontmatter,
    places: list[PlaceModel],
    days: list[ParsedDay] | None = None,
) -> None:
    """Upsert one trip + its places + days + day_places into SQLite.

    Cascade-deletes the trip first (FK ON DELETE CASCADE removes its
    children), then re-inserts. Commits at the end. Caller should validate
    day [[slug]] refs against places before calling.
    """
    days = days or []
    cur = conn.cursor()
    # Bootstrap schema if needed — first-run users shouldn't have to run
    # `tp doctor` before `tp parse`. DDL is idempotent (CREATE IF NOT EXISTS).
    cur.executescript(SCHEMA_DDL)
    cur.execute("PRAGMA foreign_keys = ON")
    cur.execute("DELETE FROM trip WHERE id = ?", (trip.trip_id,))

    cur.execute(
        """
        INSERT INTO trip
            (id, name, start_date, end_date, total_budget_kr,
             themes_json, notes_path)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trip.trip_id,
            trip.name,
            trip.start_date.isoformat() if trip.start_date else None,
            trip.end_date.isoformat() if trip.end_date else None,
            trip.total_budget_kr,
            json.dumps(trip.themes),
            trip.notes_path,
        ),
    )

    cur.executemany(
        """
        INSERT INTO place
            (id, trip_id, name_en, name_local, category, address,
             lat, lng, google_place_id, tags_json, urls_json, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                p.id,
                trip.trip_id,
                p.name_en,
                p.name_local,
                p.category,
                p.address,
                p.lat,
                p.lng,
                p.google_place_id,
                json.dumps(p.tags),
                json.dumps(p.urls),
                p.notes,
            )
            for p in places
        ],
    )

    for day in days:
        cur.execute(
            """
            INSERT INTO day
                (trip_id, day_number, date, location, title, notes_path)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                trip.trip_id,
                day.frontmatter.day_number,
                day.frontmatter.date.isoformat() if day.frontmatter.date else None,
                day.frontmatter.location,
                day.frontmatter.title,
                day.notes_path,
            ),
        )
        day_id = cur.lastrowid
        for ref in day.place_refs:
            cur.execute(
                """
                INSERT INTO day_place
                    (day_id, trip_id, place_id, time_slot, order_in_day, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    day_id,
                    trip.trip_id,
                    ref.place_slug,
                    None,  # time_slot — inferred from headings in a later milestone
                    ref.order_in_day,
                    None,
                ),
            )

    conn.commit()
