"""Day file parsing: frontmatter + [[slug]] reference extraction.

Each `trips/<slug>/days/day-NN.md` has YAML frontmatter for day metadata and
a prose body. Place references in prose use Obsidian-style `[[slug]]`
syntax (with optional `[[slug|alias]]`). First-appearance order of unique
slugs becomes `order_in_day` in the `day_place` join.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as date_t
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from ruamel.yaml import YAML

from travel_planner.parser.trip import split_frontmatter

_yaml_reader = YAML(typ="safe")

# [[slug]] or [[slug|some alias text]] — captured group is always the slug.
# Slug grammar matches parser/places.py (leading digit allowed).
_slug_ref_pattern = re.compile(r"\[\[([a-z0-9]+(?:-[a-z0-9]+)*)(?:\|[^\]]*)?\]\]")
# Matches day-01.md, day-02.md, ..., day-100.md
_day_filename_pattern = re.compile(r"^day-(\d{2,3})\.md$")


class DayFrontmatter(BaseModel):
    """Validated YAML frontmatter from a day file."""

    day_number: int
    # Use date_t for the annotation; otherwise the field name `date` shadows
    # the imported type when pydantic resolves the annotation on Python 3.14+.
    date: date_t | None = None
    location: str | None = None
    title: str | None = None


@dataclass
class DayPlaceRef:
    """A single [[slug]] reference in a day's prose."""

    place_slug: str
    order_in_day: int


@dataclass
class ParsedDay:
    """One day file: frontmatter + refs + path-back-to-source."""

    frontmatter: DayFrontmatter
    place_refs: list[DayPlaceRef]
    notes_path: str  # relative to repo root


def extract_slug_refs(body: str) -> list[str]:
    """Return unique [[slug]] refs in order of first appearance."""
    seen: set[str] = set()
    ordered: list[str] = []
    for match in _slug_ref_pattern.finditer(body):
        slug = match.group(1)
        if slug not in seen:
            seen.add(slug)
            ordered.append(slug)
    return ordered


def parse_day_file(day_md: Path, repo_root: Path) -> ParsedDay:
    """Load one day-NN.md file into a ParsedDay."""
    if not day_md.exists():
        raise FileNotFoundError(f"Day file not found at {day_md}")

    text = day_md.read_text(encoding="utf-8")
    yaml_block, body = split_frontmatter(text)
    if not yaml_block.strip():
        raise ValueError(f"{day_md}: no frontmatter")
    raw: Any = _yaml_reader.load(yaml_block) or {}
    fm = DayFrontmatter.model_validate(raw)

    fn_match = _day_filename_pattern.match(day_md.name)
    if fn_match:
        fn_number = int(fn_match.group(1))
        if fn_number != fm.day_number:
            raise ValueError(
                f"{day_md.name}: filename day_number={fn_number} "
                f"doesn't match frontmatter day_number={fm.day_number}"
            )

    refs = [
        DayPlaceRef(place_slug=slug, order_in_day=i)
        for i, slug in enumerate(extract_slug_refs(body))
    ]
    notes_path = str(day_md.relative_to(repo_root))
    return ParsedDay(frontmatter=fm, place_refs=refs, notes_path=notes_path)


def load_days(days_dir: Path, repo_root: Path) -> list[ParsedDay]:
    """Load all day-NN.md files from a days dir, sorted by day_number.

    Missing directory → empty list (a trip without day files is valid).
    Duplicate `day_number` across files → ValueError.
    """
    if not days_dir.is_dir():
        return []

    parsed: list[ParsedDay] = []
    for path in sorted(days_dir.iterdir()):
        if not _day_filename_pattern.match(path.name):
            continue
        parsed.append(parse_day_file(path, repo_root))

    seen: set[int] = set()
    for d in parsed:
        if d.frontmatter.day_number in seen:
            raise ValueError(f"duplicate day_number={d.frontmatter.day_number} across day files")
        seen.add(d.frontmatter.day_number)

    parsed.sort(key=lambda d: d.frontmatter.day_number)
    return parsed


def validate_day_refs(
    days: list[ParsedDay],
    valid_place_ids: set[str],
) -> list[str]:
    """Return list of error messages for dangling [[slug]] references.

    Empty list means everything resolves. Caller (CLI) decides whether to
    abort or continue.
    """
    errors: list[str] = []
    for day in days:
        for ref in day.place_refs:
            if ref.place_slug not in valid_place_ids:
                errors.append(
                    f"day-{day.frontmatter.day_number:02d}.md references "
                    f"[[{ref.place_slug}]] but no such place in places.yaml"
                )
    return errors
