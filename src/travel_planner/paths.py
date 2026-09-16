"""Repo path resolution, shared by the CLI and the MCP server.

The CLI can lean on cwd because it is run from inside the repo. The MCP
server cannot: Claude Code launches it with whatever working directory it
happens to have, and a cwd-relative database path silently creates an empty
DB somewhere else and then reports that you have no watches. So resolution
walks up from this module's own location first, which is stable regardless
of how the process was started.
"""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """The travel-planner repo root, identified by pyproject.toml.

    Honours TP_REPO_ROOT if set, then walks up from this file, then from cwd.
    """
    override = os.environ.get("TP_REPO_ROOT")
    if override:
        return Path(override).expanduser().resolve()

    for start in (Path(__file__).resolve(), Path.cwd().resolve()):
        for parent in (start, *start.parents):
            if (parent / "pyproject.toml").exists():
                return parent
    return Path.cwd().resolve()


def data_dir() -> Path:
    d = repo_root() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def planning_db_path() -> Path:
    """The regenerable index built by `tp parse`. Safe to delete."""
    return data_dir() / "travel_planner.db"


def observations_db_path() -> Path:
    """Watch targets and availability history. NOT regenerable — see PLAN-PHASE2.md."""
    return data_dir() / "observations.db"


def discovery_cache_path() -> Path:
    """Short-lived normalized discovery candidates, used between MCP tools."""
    return data_dir() / "discovery_candidates.json"


def trips_dir() -> Path:
    return repo_root() / "trips"


def trip_dir(slug: str) -> Path:
    return trips_dir() / slug


def places_yaml(slug: str) -> Path:
    return trip_dir(slug) / "places.yaml"


def shortlist_yaml(slug: str) -> Path:
    return trip_dir(slug) / "shortlist.yaml"


def watch_log_md(slug: str) -> Path:
    return trip_dir(slug) / "watch-log.md"
