"""Availability watching: snapshot, diff, report.

Small ryokan and minshuku open their calendars for a given date somewhere
between three and six months out, on no published schedule and with no
notification. Re-checking a dozen inns across a two-week window by hand is
the job this replaces, but only for properties known to publish availability
through Rakuten.

The interesting transition is OPENED: nothing bookable through Rakuten
yesterday, something bookable through Rakuten today. Everything else is
secondary.

Deliberately NOT doing: booking, holding, or anything touching a write path.
There isn't one. The output is a reserveUrl and the last thirty seconds stay
human.

Rewritten from the reference implementation with the defects listed in
PLAN-PHASE2.md §7 fixed: reactivation, snapshot-on-change, deterministic
latest-snapshot ordering, multi-night price honesty, and typing that survives
mypy --strict.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal, Protocol, TypedDict

from travel_planner.format import yen, yen_kr
from travel_planner.lodging.rakuten import Hotel

Transition = Literal["opened", "closed", "new_plan", "price_drop"]


class VacancySource(Protocol):
    """What the watcher needs from a Rakuten client, and nothing more.

    Keeps poll() testable against a scripted fake without constructing a real
    client (which demands credentials and would hit the network).
    """

    def vacancy(
        self,
        checkin: date,
        checkout: date,
        *,
        hotel_nos: Iterable[int] | None = ...,
        adults: int = ...,
        rooms: int = ...,
    ) -> list[Hotel]: ...


class PollError(RuntimeError):
    """Some date batches could not be polled; every other batch still was.

    `changes` carries what those other batches found. They are already logged,
    so a caller can report them alongside the failure.
    """

    def __init__(self, message: str, changes: list[Change]) -> None:
        super().__init__(message)
        self.changes = changes


class PlanSummary(TypedDict):
    fp: str
    name: str
    total: int | None
    meals: str
    url: str | None


class Summary(TypedDict):
    available: int
    plans: list[PlanSummary]
    cheapest: int | None


@dataclass(frozen=True)
class Change:
    target_id: int
    label: str
    checkin: str
    checkout: str
    nights: int
    kind: Transition
    detail: str
    reserve_url: str | None = None

    @property
    def headline(self) -> str:
        head = {
            "opened": "OPENED",
            "closed": "closed",
            "new_plan": "new plan",
            "price_drop": "price drop",
        }[self.kind]
        return f"[{head}] {self.label}  {self.checkin} → {self.checkout}  {self.detail}"

    def __str__(self) -> str:
        line = self.headline
        return f"{line}\n         {self.reserve_url}" if self.reserve_url else line


@dataclass(frozen=True)
class TargetState:
    """A watch plus its most recent observation, for listing."""

    id: int
    label: str
    hotel_no: int
    checkin: str
    checkout: str
    adults: int
    rooms: int
    trip_id: str | None
    place_id: str | None
    active: bool
    last_polled_at: str | None
    available: bool | None
    cheapest_yen: int | None

    @property
    def nights(self) -> int:
        return nights_between(self.checkin, self.checkout)

    def describe(self) -> str:
        if self.last_polled_at is None:
            state = "never polled"
        elif self.available:
            state = f"AVAILABLE from {yen_kr(self.cheapest_yen)}"
        else:
            # Rakuten also cannot reveal whether this inn distributes plan inventory
            # through its API, so "nothing bookable" has no single cause.
            state = "nothing bookable"
        seen = f"  ({self.last_polled_at[:10]})" if self.last_polled_at else ""
        return (
            f"#{self.id:<4} {self.label:<30} {self.checkin}→{self.checkout} "
            f" {self.adults}p  {state}{seen}"
        )


# ------------------------------------------------------------------ windows

def nights_between(checkin: str, checkout: str) -> int:
    return (date.fromisoformat(checkout) - date.fromisoformat(checkin)).days


def expand_window(start: date, end: date, nights: int) -> list[tuple[date, date]]:
    """Every stay of `nights` length that fits inside [start, end].

    Dates aren't locked for this trip, so a watch is usually a window rather
    than one date pair. Rakuten batches 15 hotels per call per date pair, so a
    dozen inns across a fortnight is one call per candidate date, not per inn.
    """
    if nights < 1:
        raise ValueError("nights must be at least 1")
    if end <= start:
        raise ValueError("window end must be after window start")
    out: list[tuple[date, date]] = []
    checkin = start
    while checkin + timedelta(days=nights) <= end:
        out.append((checkin, checkin + timedelta(days=nights)))
        checkin += timedelta(days=1)
    return out


# ------------------------------------------------------------------ targets

def add_target(
    conn: sqlite3.Connection,
    *,
    hotel_no: int,
    label: str,
    checkin: date,
    checkout: date,
    adults: int = 2,
    rooms: int = 1,
    trip_id: str | None = None,
    place_id: str | None = None,
    max_charge: int | None = None,
) -> tuple[int, bool]:
    """Add or reactivate a watch. Returns (target_id, is_new_or_reactivated).

    The reference implementation used INSERT OR IGNORE and then read the row
    back, which silently returned a deactivated target without reactivating
    it — a watch that looks added and never runs.
    """
    key = (hotel_no, checkin.isoformat(), checkout.isoformat(), adults, rooms)
    existing = conn.execute(
        """SELECT id, active FROM watch_target
           WHERE hotel_no=? AND checkin=? AND checkout=? AND adults=? AND rooms=?""",
        key,
    ).fetchone()

    if existing is not None:
        if existing["active"]:
            return int(existing["id"]), False
        conn.execute("UPDATE watch_target SET active = 1 WHERE id = ?", (existing["id"],))
        conn.commit()
        return int(existing["id"]), True

    cur = conn.execute(
        """INSERT INTO watch_target
           (trip_id, place_id, hotel_no, label, checkin, checkout,
            adults, rooms, max_charge, active, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)""",
        (trip_id, place_id, hotel_no, label, checkin.isoformat(),
         checkout.isoformat(), adults, rooms, max_charge, _now()),
    )
    conn.commit()
    return int(cur.lastrowid or 0), True


def add_window(
    conn: sqlite3.Connection,
    *,
    hotel_no: int,
    label: str,
    window_start: date,
    window_end: date,
    nights: int,
    adults: int = 2,
    rooms: int = 1,
    trip_id: str | None = None,
    place_id: str | None = None,
    max_charge: int | None = None,
) -> list[int]:
    """One target per candidate check-in inside the window."""
    ids: list[int] = []
    for checkin, checkout in expand_window(window_start, window_end, nights):
        target_id, _ = add_target(
            conn, hotel_no=hotel_no, label=label, checkin=checkin, checkout=checkout,
            adults=adults, rooms=rooms, trip_id=trip_id, place_id=place_id,
            max_charge=max_charge,
        )
        ids.append(target_id)
    return ids


def remove_target(conn: sqlite3.Connection, target_id: int) -> bool:
    """Deactivate a watch, keeping its history. Returns False if unknown."""
    cur = conn.execute("UPDATE watch_target SET active = 0 WHERE id = ?", (target_id,))
    conn.commit()
    return cur.rowcount > 0


def list_targets(
    conn: sqlite3.Connection,
    *,
    trip_id: str | None = None,
    include_inactive: bool = False,
) -> list[TargetState]:
    sql = """
        SELECT w.*, s.available, s.cheapest_yen
        FROM watch_target w
        LEFT JOIN availability_snapshot s ON s.id = (
            SELECT id FROM availability_snapshot
            WHERE target_id = w.id
            ORDER BY polled_at DESC, id DESC LIMIT 1)
        WHERE (:include_inactive OR w.active = 1)
          AND (:trip_id IS NULL OR w.trip_id = :trip_id)
        ORDER BY w.checkin, w.label
    """
    rows = conn.execute(
        sql, {"include_inactive": 1 if include_inactive else 0, "trip_id": trip_id}
    ).fetchall()
    return [
        TargetState(
            id=int(r["id"]),
            label=str(r["label"]),
            hotel_no=int(r["hotel_no"]),
            checkin=str(r["checkin"]),
            checkout=str(r["checkout"]),
            adults=int(r["adults"]),
            rooms=int(r["rooms"]),
            trip_id=r["trip_id"],
            place_id=r["place_id"],
            active=bool(r["active"]),
            last_polled_at=r["last_polled_at"],
            available=None if r["available"] is None else bool(r["available"]),
            cheapest_yen=r["cheapest_yen"],
        )
        for r in rows
    ]


# --------------------------------------------------------------------- poll

def poll(conn: sqlite3.Connection, client: VacancySource) -> list[Change]:
    """Poll every active target once and return the changes since last poll.

    Batches by (checkin, checkout, adults, rooms): a dozen inns on the same
    night cost one API call, not a dozen.

    A failed call skips only its own batch. The scheduled run happens once a
    day and launchd does not retry it, so one network blip must not leave every
    other date unpolled until tomorrow. Failures are recorded on the run and
    raised together as PollError once every other batch is polled and committed.
    """
    run_id = _start_run(conn)
    changes: list[Change] = []
    errors: list[str] = []
    failed = batches = polled = 0
    try:
        targets = list_targets(conn)
        groups: dict[tuple[str, str, int, int], list[TargetState]] = {}
        for t in targets:
            groups.setdefault((t.checkin, t.checkout, t.adults, t.rooms), []).append(t)
        batches = len(groups)

        for (checkin, checkout, adults, rooms), batch in groups.items():
            by_no = {t.hotel_no: t for t in batch}
            try:
                hotels = client.vacancy(
                    date.fromisoformat(checkin),
                    date.fromisoformat(checkout),
                    hotel_nos=list(by_no),
                    adults=adults,
                    rooms=rooms,
                )
            except Exception as exc:  # any client failure; the next batch may still work
                failed += 1
                if str(exc) not in errors:
                    errors.append(str(exc))
                continue
            found: dict[int, Hotel] = {h.hotel_no: h for h in hotels}

            for hotel_no, target in by_no.items():
                max_charge = _max_charge(conn, target.id)
                current = summarise(found.get(hotel_no), max_charge)
                previous = _last_snapshot(conn, target.id)
                target_changes = diff(target, previous, current)
                if previous is None or _differs(previous, current):
                    _write_snapshot(conn, target.id, current)
                for change in target_changes:
                    _log_change(conn, change)
                changes.extend(target_changes)
                _mark_polled(conn, target.id)
                polled += 1
            conn.commit()
    except Exception as exc:
        _finish_run(conn, run_id, polled, len(changes), error=str(exc)[:500])
        conn.commit()
        raise

    error = None
    if failed:
        error = f"{failed} of {batches} date batch(es) failed: {' | '.join(errors)}"
    _finish_run(conn, run_id, polled, len(changes), error=error[:500] if error else None)
    conn.commit()
    if error:
        raise PollError(error, changes)
    return changes


def summarise(hotel: Hotel | None, max_charge: int | None) -> Summary:
    if hotel is None or not hotel.is_available:
        return {"available": 0, "plans": [], "cheapest": None}

    plans: list[PlanSummary] = []
    for p in hotel.plans:
        if max_charge is not None and p.total is not None and p.total > max_charge:
            continue
        plans.append({
            "fp": p.fingerprint,
            "name": f"{p.room_name} / {p.plan_name}".strip(" /"),
            "total": p.total,
            "meals": ("夕" if p.with_dinner else "") + ("朝" if p.with_breakfast else ""),
            "url": p.reserve_url,
        })

    priced = [p["total"] for p in plans if p["total"] is not None]
    return {
        "available": 1 if plans else 0,
        "plans": plans,
        "cheapest": min(priced) if priced else None,
    }


def diff(target: TargetState, prev: Summary | None, cur: Summary) -> list[Change]:
    nights = target.nights

    def change(kind: Transition, detail: str, url: str | None = None) -> Change:
        return Change(target.id, target.label, target.checkin, target.checkout,
                      nights, kind, detail, url)

    if prev is None:
        # First observation. Only worth saying anything if it is bookable.
        if cur["available"]:
            best = _best(cur)
            return [change("opened", _price(cur, nights) + " (first check)",
                           best["url"] if best else None)]
        return []

    if cur["available"] and not prev["available"]:
        best = _best(cur)
        # OPENED subsumes everything else; don't also report its plans as new.
        return [change("opened", _price(cur, nights), best["url"] if best else None)]

    if prev["available"] and not cur["available"]:
        return [change("closed", "no longer bookable for these dates")]

    if not cur["available"]:
        return []

    out: list[Change] = []
    prev_fps = {p["fp"] for p in prev["plans"]}
    for p in cur["plans"]:
        if p["fp"] not in prev_fps:
            out.append(change("new_plan", f"{p['name']} — {yen(p['total'])} {p['meals']}".strip(),
                              p["url"]))

    prev_cheapest, cur_cheapest = prev["cheapest"], cur["cheapest"]
    if prev_cheapest and cur_cheapest and cur_cheapest < prev_cheapest:
        best = _best(cur)
        out.append(change(
            "price_drop",
            f"{yen(prev_cheapest)} → {yen_kr(cur_cheapest)}{_first_night_caveat(nights)}",
            best["url"] if best else None))

    return out


# ---------------------------------------------------------------- change log

def unseen_changes(conn: sqlite3.Connection, *, limit: int = 50) -> list[tuple[int, str]]:
    """(id, rendered line) for changes not yet shown, newest first."""
    rows = conn.execute(
        """SELECT c.id, c.detected_at, c.kind, c.detail, c.reserve_url,
                  w.label, w.checkin, w.checkout
           FROM change_log c JOIN watch_target w ON w.id = c.target_id
           WHERE c.seen = 0
           ORDER BY c.detected_at DESC, c.id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    out: list[tuple[int, str]] = []
    for r in rows:
        line = (f"[{r['kind']}] {r['label']}  {r['checkin']}→{r['checkout']}  "
                f"{r['detail']}  ({r['detected_at'][:16].replace('T', ' ')})")
        if r["reserve_url"]:
            line += f"\n         {r['reserve_url']}"
        out.append((int(r["id"]), line))
    return out


def mark_seen(conn: sqlite3.Connection, change_ids: list[int]) -> None:
    if not change_ids:
        return
    conn.executemany(
        "UPDATE change_log SET seen = 1 WHERE id = ?", [(i,) for i in change_ids]
    )
    conn.commit()


def last_runs(conn: sqlite3.Connection, limit: int = 5) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM watch_run ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()


# ------------------------------------------------------------------ internals

def _first_night_caveat(nights: int) -> str:
    # Rakuten's dailyCharge covers the FIRST night only. On a multi-night stay
    # this number is not the trip price, and saying so beats a footnote.
    return "  (first night only)" if nights > 1 else ""


def _price(summary: Summary, nights: int) -> str:
    n = len(summary["plans"])
    if summary["cheapest"]:
        return f"{n} plan(s), from {yen_kr(summary['cheapest'])}{_first_night_caveat(nights)}"
    return f"{n} plan(s)"


def _best(summary: Summary) -> PlanSummary | None:
    priced = [p for p in summary["plans"] if p["total"] is not None]
    if priced:
        return min(priced, key=lambda p: p["total"] or 0)
    return summary["plans"][0] if summary["plans"] else None


def _differs(prev: Summary, cur: Summary) -> bool:
    return (
        prev["available"] != cur["available"]
        or prev["cheapest"] != cur["cheapest"]
        or {p["fp"] for p in prev["plans"]} != {p["fp"] for p in cur["plans"]}
    )


def _max_charge(conn: sqlite3.Connection, target_id: int) -> int | None:
    row = conn.execute(
        "SELECT max_charge FROM watch_target WHERE id = ?", (target_id,)
    ).fetchone()
    return None if row is None else row["max_charge"]


def _last_snapshot(conn: sqlite3.Connection, target_id: int) -> Summary | None:
    row = conn.execute(
        """SELECT payload FROM availability_snapshot
           WHERE target_id = ? ORDER BY polled_at DESC, id DESC LIMIT 1""",
        (target_id,),
    ).fetchone()
    if row is None:
        return None
    payload: Summary = json.loads(row["payload"])
    return payload


def _write_snapshot(conn: sqlite3.Connection, target_id: int, summary: Summary) -> None:
    conn.execute(
        """INSERT INTO availability_snapshot
           (target_id, polled_at, available, plan_count, cheapest_yen, payload)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (target_id, _now(), summary["available"], len(summary["plans"]),
         summary["cheapest"], json.dumps(summary, ensure_ascii=False)),
    )


def _log_change(conn: sqlite3.Connection, change: Change) -> None:
    conn.execute(
        """INSERT INTO change_log (target_id, detected_at, kind, detail, reserve_url)
           VALUES (?, ?, ?, ?, ?)""",
        (change.target_id, _now(), change.kind, change.detail, change.reserve_url),
    )


def _mark_polled(conn: sqlite3.Connection, target_id: int) -> None:
    conn.execute("UPDATE watch_target SET last_polled_at = ? WHERE id = ?", (_now(), target_id))


def _start_run(conn: sqlite3.Connection) -> int:
    cur = conn.execute("INSERT INTO watch_run (started_at) VALUES (?)", (_now(),))
    conn.commit()
    return int(cur.lastrowid or 0)


def _finish_run(
    conn: sqlite3.Connection, run_id: int, polled: int, changes: int, error: str | None = None
) -> None:
    conn.execute(
        """UPDATE watch_run
           SET finished_at = ?, targets_polled = ?, changes_found = ?, error = ?
           WHERE id = ?""",
        (_now(), polled, changes, error, run_id),
    )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
