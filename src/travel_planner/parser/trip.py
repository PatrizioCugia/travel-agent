"""trip.md frontmatter parsing + validation.

Extracts the YAML frontmatter from `trip.md` and validates it as a
TripFrontmatter pydantic model. The prose body is returned alongside so
callers can do their own thing with it (M2 doesn't need the body, but M4+
may).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from ruamel.yaml import YAML

_yaml_reader = YAML(typ="safe")
_frontmatter_pattern = re.compile(
    r"^---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)",
    re.DOTALL,
)


class TripFrontmatter(BaseModel):
    """Validated YAML frontmatter from trip.md."""

    trip_id: str
    name: str
    start_date: date | None = None
    end_date: date | None = None
    total_budget_kr: int | None = None
    themes: list[str] = Field(default_factory=list)
    notes_path: str | None = None


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split a markdown string into (frontmatter_yaml, body).

    Returns ("", text) if no frontmatter is present. Raises ValueError if the
    string starts with `---` but the closing delimiter is malformed.
    """
    if not text.startswith("---"):
        return "", text
    match = _frontmatter_pattern.match(text)
    if not match:
        raise ValueError("file starts with '---' but frontmatter is malformed")
    return match.group(1), text[match.end() :]


def load_trip_frontmatter(trip_md: Path, repo_root: Path | None = None) -> TripFrontmatter:
    """Load and validate trip.md's frontmatter.

    If `repo_root` is given and the frontmatter doesn't already declare
    `notes_path`, we set it to `trip_md` relative to repo_root — so the DB
    has a back-pointer to the canonical markdown.
    """
    if not trip_md.exists():
        raise FileNotFoundError(f"trip.md not found at {trip_md}")
    text = trip_md.read_text(encoding="utf-8")
    yaml_block, _body = split_frontmatter(text)
    if not yaml_block.strip():
        raise ValueError(f"trip.md at {trip_md} has no frontmatter")
    raw: Any = _yaml_reader.load(yaml_block) or {}
    fm = TripFrontmatter.model_validate(raw)
    if repo_root is not None and fm.notes_path is None:
        fm.notes_path = str(trip_md.relative_to(repo_root))
    return fm
