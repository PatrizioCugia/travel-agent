"""Round-trip writer for places.yaml.

Uses ruamel.yaml in round-trip (non-safe) mode so comments, key order, and
quote styles are preserved when we write lat/lng/google_place_id back into
the file. PyYAML would not preserve any of this; do not switch.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

_yaml_rt = YAML()
_yaml_rt.preserve_quotes = True
# `- ` at column 0 (not indented), keys at column 2 — the standard style
# we author places.yaml in. ruamel's defaults (sequence=4, offset=2) would
# re-indent `- id:` to column 2 on round-trip; explicit settings avoid that.
_yaml_rt.indent(mapping=2, sequence=2, offset=0)
_yaml_rt.width = 4096  # don't auto-wrap long URLs/notes


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
