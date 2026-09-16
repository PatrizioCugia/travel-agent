"""Reviewed Japanese destination/operator directories for public-bath discovery.

OpenStreetMap is useful geographic coverage, but public baths are not tagged
consistently. This registry fills explicitly reviewed gaps from Japanese
operator or destination authorities. It is deliberately small: each entry has
a source, a review date, and a clear operational-status meaning.
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

EvidenceTier = Literal["official_facility", "official_destination", "official_municipality"]
DayUseStatus = Literal["listed", "temporarily_closed", "unknown"]

_EVIDENCE_VALUES: frozenset[str] = frozenset({
    "official_facility", "official_destination", "official_municipality",
})
_DAY_USE_VALUES: frozenset[str] = frozenset({"listed", "temporarily_closed", "unknown"})


@dataclass(frozen=True)
class BathDirectoryMember:
    """A named public bath in a reviewed Japanese operator directory."""

    member_id: str
    name: str
    name_local: str
    aliases: tuple[str, ...]
    day_use_status: DayUseStatus
    status_detail: str


@dataclass(frozen=True)
class BathDirectory:
    """A source-scoped area directory, distinct from tattoo-policy evidence."""

    directory_id: str
    name: str
    aliases: tuple[str, ...]
    authority: str
    directory_url: str
    status_url: str
    evidence_tier: EvidenceTier
    reviewed_on: str
    policy_record_id: str
    members: tuple[BathDirectoryMember, ...]


class BathingDirectoryError(ValueError):
    """The checked-in official bathing-directory registry is malformed."""


def registry_path() -> Path:
    return repo_root() / "data" / "bathing_directories.yaml"


def _text(record: Mapping[object, object], key: str, *, required: bool = True) -> str | None:
    value = record.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise BathingDirectoryError(f"{key!r} must be a non-empty string")
    return value.strip()


def _date(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError as error:
            raise BathingDirectoryError("reviewed_on must be an ISO date") from error
    raise BathingDirectoryError("reviewed_on must be an ISO date")


def _aliases(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise BathingDirectoryError("aliases must be a list")
    aliases = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if len(aliases) != len(value):
        raise BathingDirectoryError("aliases must contain non-empty strings")
    return aliases


def _choice(record: Mapping[object, object], key: str, values: frozenset[str]) -> str:
    value = _text(record, key)
    assert value is not None
    if value not in values:
        raise BathingDirectoryError(f"unsupported {key}: {value!r}")
    return value


def _member(raw: object, *, known_ids: set[str]) -> BathDirectoryMember:
    if not isinstance(raw, Mapping):
        raise BathingDirectoryError("each bath-directory member must be a mapping")
    member_id = _text(raw, "id")
    name = _text(raw, "name")
    name_local = _text(raw, "name_local")
    status_detail = _text(raw, "status_detail")
    assert member_id is not None
    assert name is not None
    assert name_local is not None
    assert status_detail is not None
    if member_id in known_ids:
        raise BathingDirectoryError(f"duplicate bath-directory member ID: {member_id}")
    known_ids.add(member_id)
    return BathDirectoryMember(
        member_id=member_id,
        name=name,
        name_local=name_local,
        aliases=_aliases(raw.get("aliases")),
        day_use_status=cast(DayUseStatus, _choice(raw, "day_use_status", _DAY_USE_VALUES)),
        status_detail=status_detail,
    )


def load_registry(path: Path | None = None) -> tuple[BathDirectory, ...]:
    """Load reviewed Japanese public-bath directories."""
    file = path or registry_path()
    if not file.exists():
        raise BathingDirectoryError(f"bathing-directory registry is missing: {file}")
    with file.open(encoding="utf-8") as handle:
        data = round_trip_yaml().load(handle)
    if not isinstance(data, Mapping):
        raise BathingDirectoryError("bathing-directory registry must be a mapping")
    raw_directories = data.get("directories")
    if not isinstance(raw_directories, list):
        raise BathingDirectoryError("bathing-directory registry requires a directories list")

    directories: list[BathDirectory] = []
    directory_ids: set[str] = set()
    member_ids: set[str] = set()
    for raw in raw_directories:
        if not isinstance(raw, Mapping):
            raise BathingDirectoryError("each bath directory must be a mapping")
        directory_id = _text(raw, "id")
        name = _text(raw, "name")
        authority = _text(raw, "authority")
        directory_url = _text(raw, "directory_url")
        status_url = _text(raw, "status_url")
        policy_record_id = _text(raw, "policy_record_id")
        assert directory_id is not None
        assert name is not None
        assert authority is not None
        assert directory_url is not None
        assert status_url is not None
        assert policy_record_id is not None
        if directory_id in directory_ids:
            raise BathingDirectoryError(f"duplicate bath-directory ID: {directory_id}")
        directory_ids.add(directory_id)
        raw_members = raw.get("members")
        if not isinstance(raw_members, list) or not raw_members:
            raise BathingDirectoryError("each bath directory requires a non-empty members list")
        directories.append(BathDirectory(
            directory_id=directory_id,
            name=name,
            aliases=_aliases(raw.get("aliases")),
            authority=authority,
            directory_url=directory_url,
            status_url=status_url,
            evidence_tier=cast(
                EvidenceTier,
                _choice(raw, "evidence_tier", _EVIDENCE_VALUES),
            ),
            reviewed_on=_date(raw.get("reviewed_on")),
            policy_record_id=policy_record_id,
            members=tuple(_member(member, known_ids=member_ids) for member in raw_members),
        ))
    return tuple(directories)


def _key(text: str) -> str:
    return "".join(char for char in normalize("NFKC", text).casefold() if char.isalnum())


def find(
    near: str,
    path: Path | None = None,
) -> tuple[BathDirectory, BathDirectoryMember | None] | None:
    """Return an exact reviewed area or facility match; never fuzzy-match places."""
    needle = _key(near)
    if not needle:
        return None
    for directory in load_registry(path):
        if needle == _key(directory.name) or any(
            needle == _key(alias) for alias in directory.aliases
        ):
            return directory, None
        for member in directory.members:
            names = (member.name, member.name_local, *member.aliases)
            if any(needle == _key(name) for name in names):
                return directory, member
    return None


def _status_label(status: DayUseStatus) -> str:
    return {
        "listed": "day-use schedule published",
        "temporarily_closed": "temporarily closed",
        "unknown": "day-use status unknown",
    }[status]


def render(near: str, path: Path | None = None) -> str | None:
    """Render an official directory match, or ``None`` when none is reviewed."""
    match = find(near, path)
    if match is None:
        return None
    directory, selected = match
    lines = [
        f"{directory.name} — official Japanese public-bath directory",
        f"Authority: {directory.authority} · reviewed {directory.reviewed_on}",
        directory.directory_url,
        f"Current-status source: {directory.status_url}",
    ]
    if selected is not None:
        lines.extend([
            "",
            f"{selected.name_local} / {selected.name} — {_status_label(selected.day_use_status)}",
            selected.status_detail,
            f"Tattoo/day-use policy: bathing_access({selected.name_local!r})",
        ])
    else:
        lines.extend(["", "Named public baths:"])
        for member in directory.members:
            lines.append(
                f"- {member.name_local} / {member.name} — {_status_label(member.day_use_status)}"
            )
        lines.extend([
            "",
            "Use bathing_access with the exact Japanese bath name for reviewed tattoo policy. "
            "Listed means an official schedule exists; it is not a real-time open signal.",
        ])
    return "\n".join(lines)
