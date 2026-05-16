"""Tests for parser/day.py — day frontmatter + [[slug]] extraction."""

from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from travel_planner.parser.day import (
    DayFrontmatter,
    extract_slug_refs,
    load_days,
    parse_day_file,
    validate_day_refs,
)

REPO_ROOT = Path(__file__).parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "trips" / "test-trip-01"


def test_extract_slug_refs_returns_unique_ordered() -> None:
    body = "Visit [[place-a]], then [[place-b]], then [[place-a]] again."
    assert extract_slug_refs(body) == ["place-a", "place-b"]


def test_extract_slug_refs_handles_obsidian_alias() -> None:
    body = "Stop at [[test-cafe-1|the cafe]] for coffee."
    assert extract_slug_refs(body) == ["test-cafe-1"]


def test_extract_slug_refs_ignores_regular_markdown_links() -> None:
    body = "See [the docs](https://example.com) or [[real-place]]."
    assert extract_slug_refs(body) == ["real-place"]


def test_extract_slug_refs_rejects_invalid_slug_format() -> None:
    body = "Bad: [[BAD_SLUG]] and [[--leading-hyphen]] and [[CamelCase]]."
    assert extract_slug_refs(body) == []


def test_extract_slug_refs_empty_string() -> None:
    assert extract_slug_refs("") == []


def test_parse_day_file_fixture_day_01() -> None:
    day = parse_day_file(FIXTURE / "days" / "day-01.md", REPO_ROOT)
    assert day.frontmatter.day_number == 1
    assert day.frontmatter.date == date(2026, 1, 1)
    assert day.frontmatter.location == "Testtown"
    assert day.frontmatter.title == "Arrival, settle in"
    assert [r.place_slug for r in day.place_refs] == ["test-cafe-1"]
    assert day.place_refs[0].order_in_day == 0
    assert day.notes_path == "tests/fixtures/trips/test-trip-01/days/day-01.md"


def test_parse_day_file_fixture_day_02_dedup_and_order() -> None:
    day = parse_day_file(FIXTURE / "days" / "day-02.md", REPO_ROOT)
    # First appearance order: shrine then cafe; cafe appears twice but only once in refs
    assert [r.place_slug for r in day.place_refs] == ["test-shrine-1", "test-cafe-1"]
    assert [r.order_in_day for r in day.place_refs] == [0, 1]


def test_parse_day_file_missing_frontmatter(tmp_path: Path) -> None:
    f = tmp_path / "day-01.md"
    f.write_text("No frontmatter here.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no frontmatter"):
        parse_day_file(f, tmp_path)


def test_parse_day_file_filename_day_number_mismatch(tmp_path: Path) -> None:
    f = tmp_path / "day-01.md"
    f.write_text(
        textwrap.dedent("""\
        ---
        day_number: 5
        ---
        """),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="doesn't match"):
        parse_day_file(f, tmp_path)


def test_day_frontmatter_invalid_day_number() -> None:
    with pytest.raises(ValidationError):
        DayFrontmatter.model_validate({"day_number": "not-an-int"})


def test_load_days_fixture() -> None:
    days = load_days(FIXTURE / "days", REPO_ROOT)
    assert len(days) == 2
    assert [d.frontmatter.day_number for d in days] == [1, 2]


def test_load_days_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert load_days(tmp_path / "no-such-dir", tmp_path) == []


def test_load_days_duplicate_day_numbers(tmp_path: Path) -> None:
    (tmp_path / "day-01.md").write_text("---\nday_number: 1\n---\n", encoding="utf-8")
    (tmp_path / "day-02.md").write_text("---\nday_number: 1\n---\n", encoding="utf-8")
    with pytest.raises(ValueError, match="filename day_number=2 doesn't match"):
        # First file caught first: filename day-02 says 2 but frontmatter says 1
        load_days(tmp_path, tmp_path)


def test_validate_day_refs_finds_dangling() -> None:
    days = load_days(FIXTURE / "days", REPO_ROOT)
    errors = validate_day_refs(days, {"test-cafe-1"})  # missing test-shrine-1
    assert len(errors) == 1
    assert "test-shrine-1" in errors[0]
    assert "day-02" in errors[0]


def test_validate_day_refs_all_resolve() -> None:
    days = load_days(FIXTURE / "days", REPO_ROOT)
    errors = validate_day_refs(days, {"test-cafe-1", "test-shrine-1"})
    assert errors == []
