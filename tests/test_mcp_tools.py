"""Smoke tests for MCP tool wrappers, against a scripted Rakuten fake.

The providers have their own tests. These pin what only the wrappers decide:
how a price is labelled, and that bad input, missing keys, or a bad file come
back as an answer the model can act on rather than a raised exception.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from travel_planner import mcp_server
from travel_planner.lodging import watch
from travel_planner.lodging.rakuten import Hotel, Plan, RakutenError


def _plan(total: int, unit: int, flag: int) -> Plan:
    return Plan(room_name="和室", plan_name="1泊2食付", plan_id="1", total=total,
                charge_flag=flag, unit_charge=unit, with_dinner=True, with_breakfast=True,
                reserve_url=None)


def _hotel(plans: list[Plan]) -> Hotel:
    return Hotel(hotel_no=56699, name="湯原温泉　我無らん", kana=None, lat=35.2, lng=133.8,
                 address="岡山県真庭市", telephone=None, nearest_station=None,
                 info_url=None, plan_list_url=None, review_average=4.5, review_count=30,
                 plans=plans)


class FakeRakuten:
    def __init__(self, hotels: list[Hotel]) -> None:
        self.hotels = hotels
        self.calls = 0

    def vacancy(self, checkin: date, checkout: date, **_: Any) -> list[Hotel]:
        self.calls += 1
        return self.hotels


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeRakuten]:
    client = FakeRakuten([_hotel([_plan(total=22000, unit=11000, flag=0)])])
    monkeypatch.setattr(mcp_server, "_client", client)
    monkeypatch.delenv("JPY_PER_DKK", raising=False)        # yen only, no kroner suffix
    yield client


def test_check_availability_labels_the_party_total_and_the_unit_price(
    fake: FakeRakuten,
) -> None:
    text = mcp_server.check_availability(56699, "2027-03-11", "2027-03-13")
    assert "¥22,000 total · ¥11,000 per person" in text
    assert "Totals: 2 adult(s), 1 room(s), first night only." in text
    assert "¥22,000 per person" not in text      # the old mislabel


def test_reversed_or_malformed_dates_never_reach_rakuten(fake: FakeRakuten) -> None:
    reversed_stay = mcp_server.check_availability(56699, "2027-03-13", "2027-03-11")
    assert reversed_stay.startswith("Availability check failed: checkout 2027-03-11 must be after")
    malformed = mcp_server.find_lodging("Kinosaki Onsen", "2027-3-11", "2027-03-12")
    assert malformed.startswith("Lodging search failed: dates must be YYYY-MM-DD")
    assert fake.calls == 0


def test_missing_rakuten_keys_are_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "_client", None)
    monkeypatch.delenv("RAKUTEN_APP_ID", raising=False)
    monkeypatch.delenv("RAKUTEN_ACCESS_KEY", raising=False)
    text = mcp_server.resolve_inn("湯原温泉 我無らん")
    assert text.startswith("Inn lookup failed: Set RAKUTEN_APP_ID and RAKUTEN_ACCESS_KEY")


def test_provider_rejection_is_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    class Rejecting:
        def detail(self, hotel_no: int) -> Hotel | None:
            raise RakutenError("403 from Rakuten: allowlist")

    monkeypatch.setattr(mcp_server, "_client", Rejecting())
    assert mcp_server.lodging_detail(56699) == "Facility lookup failed: 403 from Rakuten: allowlist"


def test_watch_run_reports_partial_results_and_the_failure(
    monkeypatch: pytest.MonkeyPatch, fake: FakeRakuten
) -> None:
    opened = watch.Change(1, "Test inn", "2027-03-02", "2027-03-03", 1, "opened", "1 plan(s)")

    def partial(conn: object, client: object) -> list[watch.Change]:
        raise watch.PollError("1 of 2 date batch(es) failed: 403", [opened])

    monkeypatch.setattr(mcp_server, "_obs", lambda: None)
    monkeypatch.setattr(watch, "poll", partial)
    text = mcp_server.watch_run()
    assert text.startswith("[OPENED] Test inn")
    assert text.endswith("Incomplete run: 1 of 2 date batch(es) failed: 403")


def test_watch_add_rejects_a_reversed_stay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "_obs", lambda: None)
    text = mcp_server.watch_add(56699, "Test inn", checkin="2027-03-12", checkout="2027-03-11")
    assert text.startswith("Cannot add watch: checkout 2027-03-11 must be after")


def _demo_trip(root: Path) -> Path:
    (root / "pyproject.toml").write_text("", encoding="utf-8")
    trip_dir = root / "trips" / "demo-2027-01"
    (trip_dir / "days").mkdir(parents=True)
    trip_dir.joinpath("trip.md").write_text(
        "---\ntrip_id: demo-2027-01\nname: Demo Trip\n---\n", encoding="utf-8"
    )
    trip_dir.joinpath("places.yaml").write_text(
        "- id: station\n  name_en: Station\n  category: transit\n  lat: 34.68\n  lng: 135.82\n"
        "- id: nigatsudo\n  name_en: Nigatsudo\n  category: temple\n  lat: 34.69\n  lng: 135.84\n",
        encoding="utf-8",
    )
    trip_dir.joinpath("days/day-01.md").write_text(
        "---\nday_number: 1\n---\n[[station]] then [[nigatsudo]].\n", encoding="utf-8"
    )
    return trip_dir


def test_day_feasibility_needs_no_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _demo_trip(tmp_path)
    monkeypatch.setenv("TP_REPO_ROOT", str(tmp_path))
    text = mcp_server.check_day_feasibility("demo", 1, "walking")
    assert "Station → Nigatsudo" in text
    assert "travelmode=walking" in text
    assert mcp_server.check_day_feasibility("demo", 2) == (
        "Day 2 has no day file in trips/demo-2027-01/days."
    )


def test_malformed_shortlist_is_reported_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trip_dir = _demo_trip(tmp_path)
    monkeypatch.setenv("TP_REPO_ROOT", str(tmp_path))
    trip_dir.joinpath("shortlist.yaml").write_text("- id: x\n  name_en: [oops\n", "utf-8")
    assert mcp_server.shortlist_show("demo-2027-01").startswith("Cannot read shortlist:")
    assert "shortlist unreadable:" in mcp_server.trip_overview("demo")

