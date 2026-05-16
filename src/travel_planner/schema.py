"""Data schema for travel-planner.

Three tables (trip, place, day) + one join (day_place). Markdown is canonical;
SQLite is a regenerable index built by `tp parse`. The schema is intentionally
small — see [[feedback-bias-to-simple]] in agent memory for the rationale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

PLACE_CATEGORIES: frozenset[str] = frozenset(
    {
        "restaurant",
        "accommodation",
        "sight",
        "shop",
        "bar",
        "cafe",
        "market",
        "transit",
        "shrine",
        "temple",
        "garden",
        "museum",
        "onsen",
        "ropeway",
        "viewpoint",
    }
)


@dataclass
class Trip:
    id: str
    name: str
    start_date: date | None = None
    end_date: date | None = None
    total_budget_kr: int | None = None
    themes: list[str] = field(default_factory=list)
    notes_path: str | None = None
    my_maps_url: str | None = None
    my_maps_generated_at: datetime | None = None


@dataclass
class Place:
    id: str
    trip_id: str
    name_en: str
    category: str
    name_local: str | None = None
    address: str | None = None
    lat: float | None = None
    lng: float | None = None
    google_place_id: str | None = None
    tags: list[str] = field(default_factory=list)
    urls: dict[str, str] = field(default_factory=dict)
    notes: str | None = None


@dataclass
class Day:
    trip_id: str
    day_number: int
    id: int | None = None
    date: date | None = None
    location: str | None = None
    title: str | None = None
    notes_path: str | None = None


@dataclass
class DayPlace:
    day_id: int
    trip_id: str
    place_id: str
    order_in_day: int
    time_slot: str | None = None
    notes: str | None = None


SCHEMA_DDL: str = """
CREATE TABLE IF NOT EXISTS trip (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    total_budget_kr INTEGER,
    themes_json TEXT NOT NULL DEFAULT '[]',
    notes_path TEXT,
    my_maps_url TEXT,
    my_maps_generated_at TEXT
);

CREATE TABLE IF NOT EXISTS place (
    id TEXT NOT NULL,
    trip_id TEXT NOT NULL REFERENCES trip(id) ON DELETE CASCADE,
    name_en TEXT NOT NULL,
    name_local TEXT,
    category TEXT NOT NULL,
    address TEXT,
    lat REAL,
    lng REAL,
    google_place_id TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    urls_json TEXT NOT NULL DEFAULT '{}',
    notes TEXT,
    PRIMARY KEY (trip_id, id)
);

CREATE TABLE IF NOT EXISTS day (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id TEXT NOT NULL REFERENCES trip(id) ON DELETE CASCADE,
    day_number INTEGER NOT NULL,
    date TEXT,
    location TEXT,
    title TEXT,
    notes_path TEXT,
    UNIQUE (trip_id, day_number)
);

CREATE TABLE IF NOT EXISTS day_place (
    day_id INTEGER NOT NULL REFERENCES day(id) ON DELETE CASCADE,
    trip_id TEXT NOT NULL,
    place_id TEXT NOT NULL,
    time_slot TEXT,
    order_in_day INTEGER NOT NULL,
    notes TEXT,
    PRIMARY KEY (day_id, place_id),
    FOREIGN KEY (trip_id, place_id) REFERENCES place(trip_id, id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_place_trip ON place(trip_id);
CREATE INDEX IF NOT EXISTS idx_place_category ON place(trip_id, category);
CREATE INDEX IF NOT EXISTS idx_day_trip ON day(trip_id, day_number);
CREATE INDEX IF NOT EXISTS idx_day_place_day ON day_place(day_id, order_in_day);
""".strip()
