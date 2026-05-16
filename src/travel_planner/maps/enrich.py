"""Orchestrate places.yaml enrichment: lookup, cache, write-back, miss-report.

Pure orchestration — composes `places_lookup`, `cache`, `yaml_writer`. The
CLI is a thin wrapper around `enrich_places()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from travel_planner.maps.cache import PlacesCache
from travel_planner.maps.places_lookup import LookupResult, lookup_with_scoring
from travel_planner.maps.yaml_writer import update_places_yaml
from travel_planner.parser.places import PlaceModel

CACHE_NAMESPACE = "places_textsearch_v1"


@dataclass
class EnrichmentReport:
    needed_lookup: int = 0
    new_matches: int = 0  # successful API lookups (not just HTTP calls)
    cache_hits: int = 0
    updates_applied: int = 0
    misses: list[tuple[str, str]] = field(default_factory=list)
    enriched_ids: list[str] = field(default_factory=list)


def _needs_lookup(p: PlaceModel) -> bool:
    return p.lat is None or p.lng is None or not p.google_place_id


def _cache_query_id(p: PlaceModel) -> str:
    return f"{p.name_en}||{p.name_local or ''}||{p.address or ''}"


def _result_to_cache_dict(r: LookupResult) -> dict[str, Any]:
    return {
        "place_id": r.place_id,
        "lat": r.lat,
        "lng": r.lng,
        "name": r.name,
        "formatted_address": r.formatted_address,
        "confidence": r.confidence,
        "query_used": r.query_used,
        "language_used": r.language_used,
    }


def enrich_places(
    places: list[PlaceModel],
    places_yaml_path: Path,
    cache: PlacesCache,
    api_key: str,
    *,
    force: bool = False,
) -> EnrichmentReport:
    """Look up missing lat/lng/place_id, write back to places.yaml, report.

    Mutates places.yaml on disk (formatting/comments preserved). Saves the
    cache to disk on completion. Caller should re-load places.yaml after
    this returns if they want the enriched in-memory models.
    """
    report = EnrichmentReport()
    updates_by_id: dict[str, dict[str, Any]] = {}

    needed = [p for p in places if force or _needs_lookup(p)]
    report.needed_lookup = len(needed)

    for p in needed:
        cache_id = _cache_query_id(p)
        cached_value = None if force else cache.get(CACHE_NAMESPACE, cache_id)

        if cached_value is not None:
            result_dict = cached_value
            report.cache_hits += 1
        else:
            try:
                result = lookup_with_scoring(p.name_en, p.name_local, p.address, api_key)
            except Exception as e:
                report.misses.append((p.id, f"API error: {type(e).__name__}: {e}"))
                continue
            if result is None:
                report.misses.append((p.id, "no confident match across fallback queries"))
                continue
            result_dict = _result_to_cache_dict(result)
            cache.put(CACHE_NAMESPACE, cache_id, result_dict)
            report.new_matches += 1

        updates_by_id[p.id] = {
            "google_place_id": result_dict["place_id"],
            "lat": round(float(result_dict["lat"]), 6),
            "lng": round(float(result_dict["lng"]), 6),
        }
        report.enriched_ids.append(p.id)

    if updates_by_id:
        report.updates_applied = update_places_yaml(places_yaml_path, updates_by_id)
        cache.save()

    return report


def write_misses_report(misses: list[tuple[str, str]], output_path: Path) -> None:
    """Write `output/lookup-misses.md` listing places that need manual handling."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Lookup misses",
        "",
        "These places didn't return a confident match. Resolve by one of:",
        "",
        "1. Edit the name/address in `places.yaml` (more specific) and re-run `tp parse`.",
        "2. Look the place up manually on Google Maps, copy the place_id, and paste",
        "   into `places.yaml` under `google_place_id:` along with lat/lng.",
        "3. Remove the place from `places.yaml` if it shouldn't be on the map.",
        "",
    ]
    for slug, reason in misses:
        lines.append(f"- **`{slug}`** — {reason}")
    lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")
