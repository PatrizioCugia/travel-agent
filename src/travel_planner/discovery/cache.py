"""Small local cache for discovery candidates handed from one MCP tool to another."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from travel_planner.discovery.models import DiscoveryCandidate


class DiscoveryCache:
    """Persists normalized candidate snapshots, never raw provider responses."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._candidates: dict[str, dict[str, Any]] = {}
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                raw = {}
            candidates = raw.get("candidates") if isinstance(raw, dict) else None
            if isinstance(candidates, dict):
                self._candidates = {
                    str(key): value for key, value in candidates.items() if isinstance(value, dict)
                }

    def put_many(self, candidates: list[DiscoveryCandidate]) -> None:
        fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
        for candidate in candidates:
            value = candidate.to_dict()
            value["fetched_at"] = fetched_at
            self._candidates[candidate.candidate_id] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {"candidates": self._candidates}, ensure_ascii=False, indent=2, sort_keys=True
            ),
            encoding="utf-8",
        )

    def get(self, candidate_id: str) -> DiscoveryCandidate | None:
        raw = self._candidates.get(candidate_id)
        return DiscoveryCandidate.from_dict(raw) if raw else None
