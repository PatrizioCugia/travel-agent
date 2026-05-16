"""Smoke test for `tp doctor`. Verifies the CLI loads and runs end-to-end."""

from __future__ import annotations

import subprocess
import sys


def test_doctor_does_not_crash() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "travel_planner.cli", "doctor"],
        capture_output=True,
        text=True,
    )
    assert result.returncode in (0, 1), (
        f"unexpected exit code {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "Python" in result.stdout, f"missing Python line in: {result.stdout}"
    assert "DB writeable" in result.stdout, f"missing DB line in: {result.stdout}"


def test_schema_ddl_is_valid_sqlite() -> None:
    """The schema DDL should execute cleanly against a fresh in-memory DB."""
    import sqlite3

    from travel_planner.schema import SCHEMA_DDL

    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(SCHEMA_DDL)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not row[0].startswith("sqlite_")
        }
        assert tables == {"trip", "place", "day", "day_place"}
    finally:
        conn.close()
