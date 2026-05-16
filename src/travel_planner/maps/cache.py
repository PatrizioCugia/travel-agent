"""On-disk JSON cache for Places API responses.

Keyed by (cache_namespace, query_id) hash. Default location:
`<repo>/data/places_cache.json`. No TTL — places don't move much, and we
hit the API rarely enough that a stale-cache risk is negligible. Bypass
with `tp parse --force`.

Per Google Maps Platform ToS, place_id and lat/lng can be cached
indefinitely; other fields have a 30-day cache rule. We only cache the
narrow set we use (place_id, lat, lng, plus diagnostic metadata).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class PlacesCache:
    """JSON-backed cache, loaded eagerly, saved on `.save()`."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, Any] = {}
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data = raw
            except json.JSONDecodeError:
                # Corrupted cache, start fresh; not worth aborting parse over
                self._data = {}

    @staticmethod
    def _key(namespace: str, query_id: str) -> str:
        return hashlib.sha256(f"{namespace}|{query_id}".encode()).hexdigest()[:32]

    def get(self, namespace: str, query_id: str) -> dict[str, Any] | None:
        hit = self._data.get(self._key(namespace, query_id))
        if isinstance(hit, dict):
            return hit
        return None

    def put(self, namespace: str, query_id: str, value: dict[str, Any]) -> None:
        self._data[self._key(namespace, query_id)] = value

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    @property
    def size(self) -> int:
        return len(self._data)
