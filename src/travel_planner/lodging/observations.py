"""The observations database — world state, not plan state.

Why this is a separate file from travel_planner.db, in one paragraph:
`db/sync.py` deletes and re-inserts a whole trip on every `tp parse`, and the
schema cascades that delete to every child row. Anything observational stored
in there either carries a trip_id foreign key and gets destroyed on the next
parse, or omits the key and lies about the relationship. Availability history
cannot be regenerated from markdown — it is a record of what the outside world
did while we were watching — and losing it destroys the diff baseline the
watcher depends on. Two files make that boundary structural instead of a rule
someone has to remember. See PLAN-PHASE2.md §3.

Cross-database queries use ATTACH; see attach_planning().
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from travel_planner.paths import observations_db_path, planning_db_path

OBSERVATIONS_DDL = """
CREATE TABLE IF NOT EXISTS watch_target (
    id             INTEGER PRIMARY KEY,
    trip_id        TEXT,              -- plain column, not an FK: different database
    place_id       TEXT,
    hotel_no       INTEGER NOT NULL,
    label          TEXT NOT NULL,
    checkin        TEXT NOT NULL,     -- YYYY-MM-DD
    checkout       TEXT NOT NULL,
    adults         INTEGER NOT NULL DEFAULT 2,
    rooms          INTEGER NOT NULL DEFAULT 1,
    max_charge     INTEGER,           -- yen ceiling, optional
    active         INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL,
    last_polled_at TEXT,
    UNIQUE (hotel_no, checkin, checkout, adults, rooms)
);

CREATE TABLE IF NOT EXISTS availability_snapshot (
    id             INTEGER PRIMARY KEY,
    target_id      INTEGER NOT NULL REFERENCES watch_target(id) ON DELETE CASCADE,
    polled_at      TEXT NOT NULL,
    available      INTEGER NOT NULL,
    plan_count     INTEGER NOT NULL,
    cheapest_yen   INTEGER,
    payload        TEXT NOT NULL      -- JSON: {available, plans[], cheapest}
);

-- Written only when state actually changes, so the newest row is always the
-- current state and the table stays a readable history rather than a log of
-- "still nothing" repeated for six months.
CREATE INDEX IF NOT EXISTS idx_snapshot_target
    ON availability_snapshot (target_id, polled_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS change_log (
    id             INTEGER PRIMARY KEY,
    target_id      INTEGER NOT NULL REFERENCES watch_target(id) ON DELETE CASCADE,
    detected_at    TEXT NOT NULL,
    kind           TEXT NOT NULL,     -- opened | closed | new_plan | price_drop
    detail         TEXT NOT NULL,
    reserve_url    TEXT,
    seen           INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_change_unseen ON change_log (seen, detected_at DESC);

-- Without this, "did last night's run actually happen" is unanswerable, which
-- is how a watcher dies quietly.
CREATE TABLE IF NOT EXISTS watch_run (
    id             INTEGER PRIMARY KEY,
    started_at     TEXT NOT NULL,
    finished_at    TEXT,
    targets_polled INTEGER NOT NULL DEFAULT 0,
    changes_found  INTEGER NOT NULL DEFAULT 0,
    error          TEXT
);
""".strip()


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) the observations DB with schema applied."""
    conn = sqlite3.connect(path or observations_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(OBSERVATIONS_DDL)
    conn.commit()
    return conn


def attach_planning(conn: sqlite3.Connection, path: Path | None = None) -> bool:
    """ATTACH the planning DB as `plan` for cross-database joins.

    Returns False when the planning DB doesn't exist yet (nothing parsed),
    so callers can degrade to observation-only output instead of failing.
    """
    db = path or planning_db_path()
    if not db.exists():
        return False
    conn.execute("ATTACH DATABASE ? AS plan", (str(db),))
    return True
