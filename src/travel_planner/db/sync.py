"""SQLite sync for parsed trip + places.

Idempotent: DELETE-then-INSERT scoped to one trip_id. Re-running `tp parse`
on the same trip is safe and produces the same DB state.
"""

from __future__ import annotations

import json
import sqlite3

from travel_planner.parser.places import PlaceModel
from travel_planner.parser.trip import TripFrontmatter


def sync_trip(
    conn: sqlite3.Connection,
    trip: TripFrontmatter,
    places: list[PlaceModel],
) -> None:
    """Upsert one trip + its places into SQLite.

    Cascade-deletes the trip first (FK ON DELETE CASCADE removes its places,
    days, day_places), then re-inserts. Commits at the end.
    """
    cur = conn.cursor()
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

    conn.commit()
