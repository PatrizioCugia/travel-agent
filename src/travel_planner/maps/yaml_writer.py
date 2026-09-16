"""Round-trip writer for places.yaml.

Uses ruamel.yaml in round-trip (non-safe) mode so comments, key order, and
quote styles are preserved when we write lat/lng/google_place_id back into
the file. PyYAML would not preserve any of this; do not switch.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from travel_planner.parser.trip import split_frontmatter


def round_trip_yaml() -> YAML:
    """A ruamel instance configured for our places.yaml house style.

    `- ` at column 0 (not indented), keys at column 2 — the style we author
    places.yaml in. ruamel's defaults (sequence=4, offset=2) would re-indent
    `- id:` to column 2 on round-trip; explicit settings avoid that.

    Shared with shortlist.py so both files are written identically and a
    promoted entry doesn't reformat the file it lands in.
    """
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=2, offset=0)
    y.width = 4096  # don't auto-wrap long URLs/notes
    return y


_yaml_rt = round_trip_yaml()


def update_places_yaml(
    yaml_path: Path,
    updates_by_id: dict[str, dict[str, Any]],
) -> int:
    """Apply field updates to entries in places.yaml by `id`.

    Returns the number of entries actually modified. Entries whose `id` is
    not in `updates_by_id` are left untouched (formatting + comments
    preserved). Writes back to `yaml_path` atomically-ish (in-place open
    for write — ruamel handles serialization).
    """
    with yaml_path.open("r", encoding="utf-8") as f:
        data = _yaml_rt.load(f)

    if not isinstance(data, list):
        raise ValueError(f"{yaml_path} top level must be a YAML list")

    modified = 0
    for entry in data:
        place_id = entry.get("id")
        if place_id is None or place_id not in updates_by_id:
            continue
        for field, value in updates_by_id[place_id].items():
            entry[field] = value
        modified += 1

    with yaml_path.open("w", encoding="utf-8") as f:
        _yaml_rt.dump(data, f)

    return modified


def set_frontmatter_field(markdown_path: Path, key: str, value: Any) -> None:
    """Set one key in a Markdown file's YAML frontmatter, leaving the rest alone.

    Round-trips only the frontmatter block, so its comments and key order
    survive, and the prose body is written back byte for byte. Frontmatter is
    authored with lists indented under their key, unlike places.yaml, hence
    its own indent settings.
    """
    text = markdown_path.read_text(encoding="utf-8")
    block, body = split_frontmatter(text)
    if not block.strip():
        raise ValueError(f"{markdown_path} has no frontmatter")
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096
    data = yaml.load(block)
    if not isinstance(data, dict):
        raise ValueError(f"{markdown_path} frontmatter must be a YAML mapping")
    data[key] = value
    out = io.StringIO()
    yaml.dump(data, out)
    markdown_path.write_text(f"---\n{out.getvalue()}---\n{body}", encoding="utf-8")
