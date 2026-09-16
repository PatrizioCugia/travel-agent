"""Per-trip shortlist: candidates found by search, before they are decided on.

Why a separate file from places.yaml: places.yaml is the canonical trip place
list and it feeds the map pipeline. Thirty search candidates dumped into it
would pollute every generated artifact. So candidates live in
trips/<slug>/shortlist.yaml with an identical entry schema plus a `_found`
provenance block. Promotion removes the transient query evidence while keeping
stable `source_refs`, so a chosen place can be traced and refreshed later.

Both files are written with the same ruamel round-trip settings, so a promoted
entry doesn't reformat places.yaml on the way in.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

from ruamel.yaml.error import YAMLError

from travel_planner.format import truncate
from travel_planner.maps.yaml_writer import round_trip_yaml
from travel_planner.paths import places_yaml, shortlist_yaml

_yaml = round_trip_yaml()

SHORTLIST_HEADER = """\
# Candidates found by search, not yet part of the trip.
# `tp shortlist promote <trip> <id>` moves an entry into places.yaml.
# Entry schema matches places.yaml, plus a `_found` provenance block.
"""


def slugify(text: str, *, fallback: str = "place") -> str:
    """kebab-case ASCII slug, matching the parser's id rules.

    Japanese names romanize to nothing here, by design — callers pass an
    English name when they have one and a fallback like `rakuten-12345` when
    they don't, rather than getting a mangled slug that can never be typed.
    """
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or fallback


def _load_list(file: Path) -> list[Any]:
    """A top-level YAML list from a hand-editable file. Missing or empty → [].

    Both kinds of bad file raise ValueError naming it: ruamel's YAMLError is not
    one, and a syntax slip must not escape as a parser traceback.
    """
    if not file.exists():
        return []
    try:
        with file.open("r", encoding="utf-8") as f:
            data = _yaml.load(f)
    except YAMLError as error:
        raise ValueError(f"{file} is not valid YAML: {error}") from error
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(f"{file} must be a YAML list at top level")
    return data


def load(slug: str, path: Path | None = None) -> list[dict[str, Any]]:
    """Entries in a trip's shortlist. Missing file → empty list."""
    return list(_load_list(path or shortlist_yaml(slug)))


def save(slug: str, entries: list[dict[str, Any]], path: Path | None = None) -> None:
    # load() hands back a plain list, which drops the header comment ruamel
    # read, so the header is written every time rather than only when absent.
    file = path or shortlist_yaml(slug)
    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("w", encoding="utf-8") as f:
        f.write(SHORTLIST_HEADER)
        if entries:
            _yaml.dump(entries, f)


def unique_id(candidate: str, taken: set[str]) -> str:
    if candidate not in taken:
        return candidate
    n = 2
    while f"{candidate}-{n}" in taken:
        n += 1
    return f"{candidate}-{n}"


def _identity(entry: dict[str, Any]) -> tuple[str, Any] | None:
    """What makes this the same place: a Rakuten hotelNo or a Google place id.

    Not the name. Two different inns can share a name, and the same inn is the
    same inn whatever we ended up calling it.
    """
    if entry.get("rakuten_hotel_no") is not None:
        return ("rakuten_hotel_no", entry["rakuten_hotel_no"])
    if entry.get("google_place_id"):
        return ("google_place_id", entry["google_place_id"])
    refs = entry.get("source_refs")
    if isinstance(refs, dict):
        for provider, source_id in sorted(refs.items()):
            if isinstance(provider, str) and source_id:
                return (f"source_ref:{provider}", source_id)
    return None


def add(slug: str, entry: dict[str, Any], path: Path | None = None) -> tuple[str, bool]:
    """Append an entry. Returns (id, added).

    Adding the same place twice is a no-op. A *different* place that happens to
    slugify to a taken id gets a numbered id rather than silently vanishing.
    """
    entries = load(slug, path)
    incoming = _identity(entry)

    for existing in entries:
        if incoming is not None and _identity(existing) == incoming:
            return str(existing.get("id")), False
        if incoming is None and str(existing.get("id")) == str(entry.get("id")):
            return str(existing.get("id")), False

    taken = {str(e.get("id")) for e in entries}
    entry["id"] = unique_id(str(entry.get("id") or "place"), taken)
    entries.append(entry)
    save(slug, entries, path)
    return str(entry["id"]), True


def remove(slug: str, entry_id: str, path: Path | None = None) -> bool:
    entries = load(slug, path)
    kept = [e for e in entries if str(e.get("id")) != entry_id]
    if len(kept) == len(entries):
        return False
    save(slug, kept, path)
    return True


def promote(
    slug: str,
    entry_id: str,
    *,
    shortlist_path: Path | None = None,
    places_path: Path | None = None,
) -> dict[str, Any] | None:
    """Move an entry from shortlist.yaml into places.yaml, stripping `_found`.

    Returns the promoted entry, or None if the id isn't in the shortlist.
    After this, `sync_trip` picks it up like any hand-written place.
    """
    entries = load(slug, shortlist_path)
    match = next((e for e in entries if str(e.get("id")) == entry_id), None)
    if match is None:
        return None

    places_file = places_path or places_yaml(slug)
    places = _load_list(places_file)

    # Same test as add(): the same inn under another id is still the same inn.
    identity = _identity(match)
    for place in places:
        if str(place.get("id")) == entry_id:
            already = ""
        elif identity is not None and _identity(place) == identity:
            already = f" as {place.get('id')!r} (same {identity[0]})"
        else:
            continue
        raise ValueError(
            f"{entry_id!r} is already in places.yaml{already}. Remove it from the "
            f"shortlist with `tp shortlist remove {slug} {entry_id}` if that's the one "
            "you kept."
        )

    promoted = dict(match)
    promoted.pop("_found", None)
    places.append(promoted)

    places_file.parent.mkdir(parents=True, exist_ok=True)
    with places_file.open("w", encoding="utf-8") as f:
        _yaml.dump(places, f)

    save(slug, [e for e in entries if str(e.get("id")) != entry_id], shortlist_path)
    return promoted


# ------------------------------------------------------------ entry builders

def lodging_entry(
    *,
    hotel_no: int,
    name_en: str | None,
    name_local: str,
    address: str,
    lat: float | None = None,
    lng: float | None = None,
    google_place_id: str | None = None,
    tags: list[str] | None = None,
    notes: str | None = None,
    query: str | None = None,
    review: str | None = None,
    seen_price_yen: int | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": slugify(name_en or "", fallback=f"rakuten-{hotel_no}"),
        "name_en": name_en or name_local,
        "name_local": name_local,
        "category": "accommodation",
        "address": address,
        "rakuten_hotel_no": hotel_no,
        "tags": tags or [],
    }
    if google_place_id:
        entry["google_place_id"] = google_place_id
    if lat is not None and lng is not None:
        entry["lat"] = lat
        entry["lng"] = lng
    if notes:
        entry["notes"] = truncate(notes, 400)
    entry["_found"] = _found_block("rakuten", query, review, seen_price_yen, url)
    return entry


def food_entry(
    *,
    name: str,
    name_local: str | None,
    address: str,
    category: str = "restaurant",
    lat: float | None = None,
    lng: float | None = None,
    google_place_id: str | None = None,
    tags: list[str] | None = None,
    notes: str | None = None,
    query: str | None = None,
    review: str | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": slugify(name, fallback="restaurant"),
        "name_en": name,
        "category": category,
        "address": address,
        "tags": tags or [],
    }
    if name_local and name_local != name:
        entry["name_local"] = name_local
    if google_place_id:
        entry["google_place_id"] = google_place_id
    if lat is not None and lng is not None:
        entry["lat"] = lat
        entry["lng"] = lng
    if notes:
        entry["notes"] = truncate(notes, 400)
    entry["_found"] = _found_block("google-places", query, review, None, url)
    return entry


def activity_entry(
    *,
    source: str,
    source_id: str,
    name: str,
    name_local: str | None,
    category: str,
    address: str | None,
    lat: float,
    lng: float,
    source_url: str,
    website: str | None = None,
    tags: list[str] | None = None,
    notes: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """Build a shortlist entry from a non-booking activity discovery source."""
    entry: dict[str, Any] = {
        "id": slugify(name, fallback=f"{source}-{source_id.replace('/', '-')[:30]}"),
        "name_en": name,
        "category": category,
        "lat": lat,
        "lng": lng,
        "source_refs": {source: source_id},
        "tags": tags or [],
        "urls": {source: source_url},
    }
    if name_local and name_local != name:
        entry["name_local"] = name_local
    if address:
        entry["address"] = address
    if website:
        entry["urls"]["website"] = website
    if notes:
        entry["notes"] = truncate(notes, 400)
    entry["_found"] = _found_block(source, query, None, None, source_url)
    return entry


def render(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "Shortlist is empty."
    by_category: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        by_category.setdefault(str(e.get("category", "other")), []).append(e)

    lines: list[str] = []
    for category in sorted(by_category):
        lines.append(f"{category} ({len(by_category[category])})")
        for e in by_category[category]:
            found = e.get("_found") or {}
            bits = [str(e.get("id"))]
            name = e.get("name_en") or e.get("name_local") or "?"
            bits.append(str(name))
            if e.get("name_local") and e.get("name_local") != name:
                bits.append(str(e["name_local"]))
            line = f"  {bits[0]:<32} {' '.join(bits[1:])}"
            lines.append(line)
            meta = []
            if found.get("review"):
                meta.append(str(found["review"]))
            if found.get("seen_price_yen"):
                meta.append(f"¥{int(found['seen_price_yen']):,}")
            if e.get("rakuten_hotel_no"):
                meta.append(f"rakuten #{e['rakuten_hotel_no']}")
            if found.get("at"):
                meta.append(f"found {found['at']}")
            if meta:
                lines.append(f"  {'':<32} {' · '.join(meta)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _found_block(
    source: str,
    query: str | None,
    review: str | None,
    seen_price_yen: int | None,
    url: str | None,
) -> dict[str, Any]:
    block: dict[str, Any] = {"source": source, "at": date.today().isoformat()}
    if query:
        block["query"] = query
    if review:
        block["review"] = review
    if seen_price_yen is not None:
        block["seen_price_yen"] = seen_price_yen
    if url:
        block["url"] = url
    return block
