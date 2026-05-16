"""Tests for maps/yaml_writer.py — round-trip places.yaml writer."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from travel_planner.maps.yaml_writer import update_places_yaml


def _yaml(tmp_path: Path, content: str) -> Path:
    f = tmp_path / "places.yaml"
    f.write_text(textwrap.dedent(content), encoding="utf-8")
    return f


def test_preserves_top_level_comments(tmp_path: Path) -> None:
    src = _yaml(
        tmp_path,
        """\
        # Top-level comment
        - id: p1
          name_en: Place One
          category: cafe
        """,
    )
    update_places_yaml(src, {"p1": {"lat": 35.5}})
    contents = src.read_text(encoding="utf-8")
    assert "# Top-level comment" in contents
    assert "lat: 35.5" in contents


def test_preserves_inline_comments(tmp_path: Path) -> None:
    src = _yaml(
        tmp_path,
        """\
        - id: p1
          name_en: Place One   # an inline comment
          category: cafe
        """,
    )
    update_places_yaml(src, {"p1": {"lat": 1.0, "lng": 2.0}})
    contents = src.read_text(encoding="utf-8")
    assert "# an inline comment" in contents


def test_updates_only_matched_id(tmp_path: Path) -> None:
    src = _yaml(
        tmp_path,
        """\
        - id: p1
          name_en: P1
          category: cafe
        - id: p2
          name_en: P2
          category: shrine
        """,
    )
    update_places_yaml(src, {"p1": {"lat": 10.0}})
    contents = src.read_text(encoding="utf-8")
    assert "lat: 10.0" in contents
    # p2 should not have lat set
    p2_section = contents.split("id: p2")[1]
    assert "lat:" not in p2_section


def test_returns_modified_count(tmp_path: Path) -> None:
    src = _yaml(
        tmp_path,
        """\
        - id: p1
          name_en: P1
          category: cafe
        - id: p2
          name_en: P2
          category: shrine
        """,
    )
    n = update_places_yaml(src, {"p1": {"lat": 1.0}, "p2": {"lat": 2.0}, "p3": {"lat": 3.0}})
    assert n == 2  # only p1, p2 matched


def test_non_list_yaml_raises(tmp_path: Path) -> None:
    src = _yaml(tmp_path, "key: value\n")
    with pytest.raises(ValueError, match="YAML list"):
        update_places_yaml(src, {})


def test_preserves_block_scalar_notes(tmp_path: Path) -> None:
    src = _yaml(
        tmp_path,
        """\
        - id: p1
          name_en: P1
          category: cafe
          notes: |
            Multi-line notes
            with a second line.
        """,
    )
    update_places_yaml(src, {"p1": {"lat": 1.0}})
    contents = src.read_text(encoding="utf-8")
    assert "notes:" in contents
    assert "Multi-line notes" in contents
    assert "with a second line." in contents
