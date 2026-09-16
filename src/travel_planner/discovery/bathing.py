"""Reviewed onsen, sento, and sauna access evidence.

Location data can tell us where a bath is. It cannot safely tell us whether a
tattoo is accepted, whether a private bath is available, or whether day use is
open. Those are facility policies, so this module exposes only reviewed,
source-linked evidence from the small local registry.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal, cast
from unicodedata import normalize

from travel_planner.maps.yaml_writer import round_trip_yaml
from travel_planner.paths import repo_root

TattooStatus = Literal["allowed", "conditional", "prohibited", "unknown"]
EvidenceTier = Literal[
    "official_facility",
    "official_destination",
    "official_municipality",
    "vetted_directory",
    "community",
]
PrivateBath = Literal["yes", "no", "varies", "unknown"]

_TATTOO_VALUES: frozenset[str] = frozenset({"allowed", "conditional", "prohibited", "unknown"})
_EVIDENCE_VALUES: frozenset[str] = frozenset({
    "official_facility",
    "official_destination",
    "official_municipality",
    "vetted_directory",
    "community",
})
_PRIVATE_BATH_VALUES: frozenset[str] = frozenset({"yes", "no", "varies", "unknown"})


@dataclass(frozen=True)
class BathingAccess:
    """A source-scoped policy record, not a general rule for an onsen town."""

    record_id: str
    name: str
    aliases: tuple[str, ...]
    kind: str
    applies_to: str
    tattoo_status: TattooStatus
    tattoo_detail: str
    day_use: bool | None
    private_bath: PrivateBath
    access_url: str
    evidence_tier: EvidenceTier
    reviewed_on: str
    notes: str | None = None


class BathingAccessError(ValueError):
    """The checked-in bathing-access registry is malformed."""


def registry_path() -> Path:
    return repo_root() / "data" / "bathing_access.yaml"


def _text(record: Mapping[object, object], key: str, *, required: bool = True) -> str | None:
    value = record.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise BathingAccessError(f"{key!r} must be a non-empty string")
    return value.strip()


def _choice(record: Mapping[object, object], key: str, values: frozenset[str]) -> str:
    value = _text(record, key)
    assert value is not None
    if value not in values:
        raise BathingAccessError(f"unsupported {key}: {value!r}")
    return value


def _date(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError as error:
            raise BathingAccessError("reviewed_on must be an ISO date") from error
    raise BathingAccessError("reviewed_on must be an ISO date")


def _aliases(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise BathingAccessError("aliases must be a non-empty list")
    aliases = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if len(aliases) != len(value):
        raise BathingAccessError("aliases must contain non-empty strings")
    return aliases


def load_registry(path: Path | None = None) -> tuple[BathingAccess, ...]:
    """Load reviewed access evidence from the checked-in registry."""
    file = path or registry_path()
    if not file.exists():
        raise BathingAccessError(f"bathing-access registry is missing: {file}")
    with file.open(encoding="utf-8") as handle:
        data = round_trip_yaml().load(handle)
    if not isinstance(data, Mapping):
        raise BathingAccessError("bathing-access registry must be a mapping")
    raw_records = data.get("records")
    if not isinstance(raw_records, list):
        raise BathingAccessError("bathing-access registry requires a records list")

    records: list[BathingAccess] = []
    record_ids: set[str] = set()
    for raw in raw_records:
        if not isinstance(raw, Mapping):
            raise BathingAccessError("each bathing-access record must be a mapping")
        record_id = _text(raw, "id")
        name = _text(raw, "name")
        kind = _text(raw, "kind")
        applies_to = _text(raw, "applies_to")
        detail = _text(raw, "tattoo_detail")
        access_url = _text(raw, "access_url")
        assert record_id is not None
        assert name is not None
        assert kind is not None
        assert applies_to is not None
        assert detail is not None
        assert access_url is not None
        if record_id in record_ids:
            raise BathingAccessError(f"duplicate bathing-access ID: {record_id}")
        record_ids.add(record_id)
        day_use = raw.get("day_use")
        if day_use is not None and not isinstance(day_use, bool):
            raise BathingAccessError("day_use must be true, false, or omitted")
        records.append(BathingAccess(
            record_id=record_id,
            name=name,
            aliases=_aliases(raw.get("aliases")),
            kind=kind,
            applies_to=applies_to,
            tattoo_status=cast(TattooStatus, _choice(raw, "tattoo_status", _TATTOO_VALUES)),
            tattoo_detail=detail,
            day_use=day_use,
            private_bath=cast(PrivateBath, _choice(raw, "private_bath", _PRIVATE_BATH_VALUES)),
            access_url=access_url,
            evidence_tier=cast(EvidenceTier, _choice(raw, "evidence_tier", _EVIDENCE_VALUES)),
            reviewed_on=_date(raw.get("reviewed_on")),
            notes=_text(raw, "notes", required=False),
        ))
    return tuple(records)


def _key(text: str) -> str:
    """Normalize wording without fuzzy matching a policy onto the wrong bath."""
    return "".join(char for char in normalize("NFKC", text).casefold() if char.isalnum())


def find(name: str, path: Path | None = None) -> BathingAccess | None:
    """Match an exact normalized facility or reviewed policy-scope alias."""
    needle = _key(name)
    if not needle:
        return None
    for record in load_registry(path):
        if needle == _key(record.name) or any(needle == _key(alias) for alias in record.aliases):
            return record
    return None


def _label(value: str) -> str:
    return value.replace("_", " ").title()


def render(name: str, path: Path | None = None) -> str:
    """Render safe tattoo and access guidance for a named bath."""
    record = find(name, path)
    if record is None:
        return (
            f"No reviewed tattoo/access record for {name!r}. Status: unknown.\n"
            "Find the bath with discover_nearby. Check its official site for tattoo/刺青/入れ墨, "
            "day-use, and private-bath rules. A destination authority can confirm a shared "
            "public-bath policy; directories are leads only. If admission matters, contact the "
            "facility before going."
        )

    day_use = (
        "yes" if record.day_use is True else "no" if record.day_use is False else "not recorded"
    )
    lines = [
        f"{record.name} — {_label(record.kind)}",
        f"Tattoo status: {_label(record.tattoo_status)} — {record.tattoo_detail}",
        f"Scope: {record.applies_to}",
        f"Day use: {day_use} · private bath: {_label(record.private_bath)}",
        f"Evidence: {_label(record.evidence_tier)}, reviewed {record.reviewed_on}",
        record.access_url,
    ]
    if record.notes:
        lines.append(f"Note: {record.notes}")
    lines.append("Recheck current hours and closures with the operator before visiting.")
    return "\n".join(lines)


def audit(path: Path | None = None) -> str:
    """Summarize reviewed bathing-policy coverage without overstating it."""
    records = load_registry(path)
    statuses = {
        status: sum(record.tattoo_status == status for record in records)
        for status in _TATTOO_VALUES
    }
    official = sum(record.evidence_tier.startswith("official_") for record in records)
    return (
        f"{len(records)} reviewed bathing-policy record(s): {statuses['allowed']} allowed, "
        f"{statuses['conditional']} conditional, {statuses['prohibited']} prohibited, and "
        f"{statuses['unknown']} unknown. {official} record(s) have official-source evidence. "
        "Coverage is deliberately incomplete; absence from the registry means unknown."
    )
