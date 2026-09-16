"""Tests for the availability watcher: windows, targets, and the diff machine.

The diff is the part worth testing hardest — it decides whether you hear about
a ryokan opening its calendar, and there is no second chance at that.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from datetime import date

import pytest

from travel_planner.lodging import watch
from travel_planner.lodging.observations import OBSERVATIONS_DDL
from travel_planner.lodging.rakuten import Hotel, Plan


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(OBSERVATIONS_DDL)
    yield c
    c.close()


def _plan(name: str = "和室", plan: str = "素泊まり", total: int | None = 40000,
          plan_id: str = "1", dinner: bool = False) -> Plan:
    return Plan(room_name=name, plan_name=plan, plan_id=plan_id, total=total,
                charge_flag=0, unit_charge=None, with_dinner=dinner, with_breakfast=True,
                reserve_url="https://example.invalid/reserve")


def _hotel(plans: list[Plan] | None = None) -> Hotel:
    return Hotel(hotel_no=56699, name="湯原温泉　我無らん", kana=None, lat=35.2, lng=133.8,
                 address="岡山県真庭市", telephone=None, nearest_station=None,
                 info_url=None, plan_list_url=None, review_average=4.5, review_count=30,
                 plans=plans or [])


def _target(nights: int = 1) -> watch.TargetState:
    checkout = "2027-03-12" if nights == 1 else "2027-03-13"
    return watch.TargetState(
        id=1, label="Test inn", hotel_no=56699, checkin="2027-03-11", checkout=checkout,
        adults=2, rooms=1, trip_id="japan-2027-02", place_id=None, active=True,
        last_polled_at=None, available=None, cheapest_yen=None,
    )


# --------------------------------------------------------------------- windows

def test_expand_window_yields_every_fitting_stay() -> None:
    pairs = watch.expand_window(date(2027, 3, 1), date(2027, 3, 5), nights=2)
    assert pairs == [
        (date(2027, 3, 1), date(2027, 3, 3)),
        (date(2027, 3, 2), date(2027, 3, 4)),
        (date(2027, 3, 3), date(2027, 3, 5)),
    ]


def test_expand_window_rejects_impossible_input() -> None:
    with pytest.raises(ValueError):
        watch.expand_window(date(2027, 3, 1), date(2027, 3, 5), nights=0)
    with pytest.raises(ValueError):
        watch.expand_window(date(2027, 3, 5), date(2027, 3, 1), nights=1)


def test_window_shorter_than_stay_yields_nothing() -> None:
    assert watch.expand_window(date(2027, 3, 1), date(2027, 3, 2), nights=3) == []


# --------------------------------------------------------------------- targets

def test_add_target_is_idempotent(conn: sqlite3.Connection) -> None:
    first, created = watch.add_target(conn, hotel_no=1, label="A",
                                      checkin=date(2027, 3, 1), checkout=date(2027, 3, 2))
    second, created_again = watch.add_target(conn, hotel_no=1, label="A",
                                             checkin=date(2027, 3, 1), checkout=date(2027, 3, 2))
    assert first == second
    assert created is True and created_again is False


def test_readding_a_removed_target_reactivates_it(conn: sqlite3.Connection) -> None:
    """The reference version returned the dead row: a watch that never runs."""
    target_id, _ = watch.add_target(conn, hotel_no=1, label="A",
                                    checkin=date(2027, 3, 1), checkout=date(2027, 3, 2))
    assert watch.remove_target(conn, target_id) is True
    assert watch.list_targets(conn) == []

    again, created = watch.add_target(conn, hotel_no=1, label="A",
                                      checkin=date(2027, 3, 1), checkout=date(2027, 3, 2))
    assert again == target_id
    assert created is True
    assert [t.id for t in watch.list_targets(conn)] == [target_id]


def test_add_window_creates_one_target_per_date(conn: sqlite3.Connection) -> None:
    ids = watch.add_window(conn, hotel_no=7, label="Nara inn",
                           window_start=date(2027, 3, 1), window_end=date(2027, 3, 8),
                           nights=1, trip_id="japan-2027-02")
    assert len(ids) == 7
    assert len(watch.list_targets(conn, trip_id="japan-2027-02")) == 7
    assert watch.list_targets(conn, trip_id="other") == []


# ------------------------------------------------------------------- the diff

def test_first_sighting_of_nothing_is_silent() -> None:
    assert watch.diff(_target(), None, watch.summarise(None, None)) == []


def test_first_sighting_of_availability_reports_opened() -> None:
    changes = watch.diff(_target(), None, watch.summarise(_hotel([_plan()]), None))
    assert [c.kind for c in changes] == ["opened"]
    assert "first check" in changes[0].detail


def test_four_day_sequence() -> None:
    """closed → opened → new plan → price drop → closed."""
    nothing = watch.summarise(None, None)
    one = watch.summarise(_hotel([_plan(total=40000)]), None)
    two = watch.summarise(
        _hotel([_plan(total=40000), _plan("離れ", "夕食付", 52000, "2", True)]), None
    )
    cheaper = watch.summarise(
        _hotel([_plan(total=36000), _plan("離れ", "夕食付", 52000, "2", True)]), None
    )

    assert watch.diff(_target(), nothing, nothing) == []

    opened = watch.diff(_target(), nothing, one)
    assert [c.kind for c in opened] == ["opened"]
    assert opened[0].reserve_url == "https://example.invalid/reserve"

    added = watch.diff(_target(), one, two)
    assert [c.kind for c in added] == ["new_plan"]
    assert "離れ" in added[0].detail

    dropped = watch.diff(_target(), two, cheaper)
    assert [c.kind for c in dropped] == ["price_drop"]

    closed = watch.diff(_target(), cheaper, nothing)
    assert [c.kind for c in closed] == ["closed"]


def test_opened_subsumes_new_plans() -> None:
    """When an inn opens, every plan is new — say it once, not five times."""
    nothing = watch.summarise(None, None)
    many = watch.summarise(_hotel([_plan(total=40000), _plan("B", "b", 50000, "2")]), None)
    assert [c.kind for c in watch.diff(_target(), nothing, many)] == ["opened"]


def test_price_rise_is_not_reported() -> None:
    cheap = watch.summarise(_hotel([_plan(total=36000)]), None)
    dear = watch.summarise(_hotel([_plan(total=40000)]), None)
    assert watch.diff(_target(), cheap, dear) == []


def test_multi_night_price_says_first_night_only() -> None:
    """dailyCharge covers night one; on a 2-night stay that is not the trip price."""
    one = watch.summarise(_hotel([_plan(total=40000)]), None)
    cheaper = watch.summarise(_hotel([_plan(total=36000)]), None)
    single = watch.diff(_target(nights=1), one, cheaper)[0]
    multi = watch.diff(_target(nights=2), one, cheaper)[0]
    assert "first night" not in single.detail
    assert "first night only" in multi.detail


def test_max_charge_filters_plans_out_of_availability() -> None:
    summary = watch.summarise(_hotel([_plan(total=40000)]), 30000)
    assert summary["available"] == 0
    assert summary["plans"] == []


def test_plans_without_price_still_count_as_available() -> None:
    summary = watch.summarise(_hotel([_plan(total=None)]), 30000)
    assert summary["available"] == 1
    assert summary["cheapest"] is None


# ----------------------------------------------------------------- poll + log

class FakeClient:
    """A scripted VacancySource: no credentials, no network, no flakiness."""

    def __init__(self, responses: list[list[Hotel]]) -> None:
        self.responses = responses
        self.calls: list[tuple[date, date, list[int]]] = []

    def vacancy(
        self,
        checkin: date,
        checkout: date,
        *,
        hotel_nos: Iterable[int] | None = None,
        adults: int = 2,
        rooms: int = 1,
    ) -> list[Hotel]:
        self.calls.append((checkin, checkout, list(hotel_nos or [])))
        return self.responses.pop(0) if self.responses else []


def test_poll_writes_snapshots_only_when_state_changes(conn: sqlite3.Connection) -> None:
    watch.add_target(conn, hotel_no=56699, label="Test inn",
                     checkin=date(2027, 3, 11), checkout=date(2027, 3, 12))
    client = FakeClient([[], [], [_hotel([_plan()])], [_hotel([_plan()])]])

    assert watch.poll(conn, client) == []                      # nothing, first look
    assert watch.poll(conn, client) == []                      # still nothing
    opened = watch.poll(conn, client)                          # opens
    assert [c.kind for c in opened] == ["opened"]
    assert watch.poll(conn, client) == []                      # unchanged

    snapshots = conn.execute("SELECT count(*) FROM availability_snapshot").fetchone()[0]
    assert snapshots == 2      # one per real state change, not one per poll
    assert conn.execute("SELECT count(*) FROM watch_run").fetchone()[0] == 4


def test_poll_batches_targets_sharing_dates(conn: sqlite3.Connection) -> None:
    for hotel_no in (1, 2, 3):
        watch.add_target(conn, hotel_no=hotel_no, label=f"inn {hotel_no}",
                         checkin=date(2027, 3, 11), checkout=date(2027, 3, 12))
    client = FakeClient([[]])
    watch.poll(conn, client)
    assert len(client.calls) == 1                 # one call, three inns
    assert client.calls[0][2] == [1, 2, 3]


def test_changes_are_logged_then_marked_seen(conn: sqlite3.Connection) -> None:
    watch.add_target(conn, hotel_no=56699, label="Test inn",
                     checkin=date(2027, 3, 11), checkout=date(2027, 3, 12))
    watch.poll(conn, FakeClient([[_hotel([_plan()])]]))

    unseen = watch.unseen_changes(conn)
    assert len(unseen) == 1
    assert "OPENED" in unseen[0][1] or "opened" in unseen[0][1]

    watch.mark_seen(conn, [i for i, _ in unseen])
    assert watch.unseen_changes(conn) == []


def test_failed_run_is_recorded_and_reraised(conn: sqlite3.Connection) -> None:
    watch.add_target(conn, hotel_no=1, label="A",
                     checkin=date(2027, 3, 1), checkout=date(2027, 3, 2))

    class Broken:
        def vacancy(
            self,
            checkin: date,
            checkout: date,
            *,
            hotel_nos: Iterable[int] | None = None,
            adults: int = 2,
            rooms: int = 1,
        ) -> list[Hotel]:
            raise RuntimeError("rakuten is down")

    with pytest.raises(RuntimeError):
        watch.poll(conn, Broken())
    row = conn.execute("SELECT error FROM watch_run ORDER BY id DESC LIMIT 1").fetchone()
    assert "rakuten is down" in row["error"]


def test_target_state_describes_never_polled(conn: sqlite3.Connection) -> None:
    watch.add_target(conn, hotel_no=1, label="A",
                     checkin=date(2027, 3, 1), checkout=date(2027, 3, 2))
    assert "never polled" in watch.list_targets(conn)[0].describe()


def test_one_failed_batch_does_not_blind_the_rest_of_the_run(
    conn: sqlite3.Connection,
) -> None:
    for day in (1, 2):
        watch.add_target(conn, hotel_no=56699, label="Test inn",
                         checkin=date(2027, 3, day), checkout=date(2027, 3, day + 1))

    class FirstDateDown:
        def vacancy(
            self,
            checkin: date,
            checkout: date,
            *,
            hotel_nos: Iterable[int] | None = None,
            adults: int = 2,
            rooms: int = 1,
        ) -> list[Hotel]:
            if checkin == date(2027, 3, 1):
                raise RuntimeError("403 from Rakuten")
            return [_hotel([_plan()])]

    with pytest.raises(watch.PollError, match="1 of 2 date batch") as caught:
        watch.poll(conn, FirstDateDown())

    assert [(c.checkin, c.kind) for c in caught.value.changes] == [("2027-03-02", "opened")]
    polled = {t.checkin: t.last_polled_at for t in watch.list_targets(conn)}
    assert polled["2027-03-01"] is None and polled["2027-03-02"] is not None
    run = conn.execute("SELECT targets_polled, error FROM watch_run").fetchone()
    assert run["targets_polled"] == 1
    assert "403 from Rakuten" in run["error"]
    assert len(watch.unseen_changes(conn)) == 1                  # the opening is logged
