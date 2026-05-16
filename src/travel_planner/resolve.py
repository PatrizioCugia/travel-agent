"""Fuzzy trip-slug resolution.

Lets users type partial slugs (e.g. `nagoya`) that resolve to full ones
(e.g. `nagoya-2026-11`). Order: exact match → unique substring →
rapidfuzz partial_ratio above threshold. Ambiguity surfaces a candidate
list for the caller to handle.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from rapidfuzz import fuzz, process

FUZZY_THRESHOLD = 80.0


def list_trips(trips_dir: Path) -> list[str]:
    """List trip slugs from `trips/<slug>/` directories, skipping `_template`."""
    if not trips_dir.is_dir():
        return []
    return sorted(p.name for p in trips_dir.iterdir() if p.is_dir() and not p.name.startswith("_"))


def resolve_slug(input_slug: str, available: Sequence[str]) -> tuple[str | None, list[str]]:
    """Resolve a fuzzy slug against a list of available trip slugs.

    Returns `(slug, candidates)`:
    - `(slug, [])`: unique match. Caller uses `slug`.
    - `(None, [s1, s2, ...])`: ambiguous. Caller should ask the user.
    - `(None, [])`: no plausible match.
    """
    if not available:
        return None, []

    if input_slug in available:
        return input_slug, []

    lower = input_slug.lower()
    substring = sorted(s for s in available if lower in s.lower())
    if len(substring) == 1:
        return substring[0], []
    if len(substring) > 1:
        return None, substring

    matches = process.extract(input_slug, list(available), scorer=fuzz.partial_ratio, limit=5)
    high_conf = sorted(m[0] for m in matches if m[1] >= FUZZY_THRESHOLD)
    if len(high_conf) == 1:
        return high_conf[0], []
    if len(high_conf) > 1:
        return None, high_conf

    return None, []
