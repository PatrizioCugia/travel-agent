"""Tests for the Rakuten response parser.

The pairing test is the load-bearing one: live responses put roomBasicInfo and
dailyCharge side by side in ONE flat list, and the original implementation
zipped each element against itself, so every price parsed as None.
"""

from __future__ import annotations

from typing import Any

import pytest

from travel_planner.lodging.rakuten import RakutenError, _parse_hotel, _parse_plans

BASIC = {
    "hotelNo": 147566,
    "hotelName": "東横ＩＮＮ近鉄奈良駅前",
    "address1": "奈良県",
    "address2": "奈良市",
    "latitude": 34.683,
    "longitude": 135.828,
    "reviewAverage": 4.08,
    "reviewCount": 508,
    "nearestStation": "近鉄奈良",
}


def _room(
    name: str = "喫煙エコノミーダブル", plan_id: int = 3329149, breakfast: int = 1
) -> dict[str, Any]:
    return {
        "roomBasicInfo": {
            "roomName": name,
            "planName": "【無料の元気朝食付】",
            "planId": plan_id,
            "withDinnerFlag": 0,
            "withBreakfastFlag": breakfast,
            "reserveUrl": "https://img.travel.rakuten.co.jp/image/tr/api/re/x/?f_no=147566",
        }
    }


def _charge(total: int = 9976) -> dict[str, Any]:
    return {"dailyCharge": {"stayDate": "2027-03-11", "rakutenCharge": total // 2,
                            "total": total, "chargeFlag": 0}}


def test_flat_room_info_pairs_charge_with_room() -> None:
    """The live shape: [{roomBasicInfo}, {dailyCharge}] in one flat list."""
    plans = _parse_plans([_room(), _charge(9976)])
    assert len(plans) == 1
    assert plans[0].total == 9976
    assert plans[0].with_breakfast is True
    assert plans[0].charge_flag == 0


def test_multiple_flat_plans_do_not_bleed_into_each_other() -> None:
    plans = _parse_plans([
        _room("A", 1), _charge(8000),
        _room("B", 2), _charge(12000),
    ])
    assert [(p.room_name, p.total) for p in plans] == [("A", 8000), ("B", 12000)]


def test_nested_room_info_still_parses() -> None:
    """Defensive: a nested shape must not regress if Rakuten ever returns one."""
    plans = _parse_plans([[_room("A", 1), _charge(8000)], [_room("B", 2), _charge(12000)]])
    assert [(p.room_name, p.total) for p in plans] == [("A", 8000), ("B", 12000)]


def test_room_without_charge_keeps_price_none() -> None:
    plans = _parse_plans([_room()])
    assert len(plans) == 1
    assert plans[0].total is None


def test_parse_hotel_reads_basic_info_and_plans() -> None:
    hotel = _parse_hotel([{"hotelBasicInfo": BASIC}, {"roomInfo": [_room(), _charge(9976)]}])
    assert hotel.hotel_no == 147566
    assert hotel.address == "奈良県奈良市"
    assert hotel.is_available is True
    assert hotel.cheapest is not None
    assert hotel.cheapest.total == 9976
    assert hotel.page_url == "https://travel.rakuten.co.jp/HOTEL/147566/147566.html"


def test_parse_hotel_without_hotel_no_raises() -> None:
    """Defaulting to 0 produced rows that looked real and could never be requeried."""
    with pytest.raises(RakutenError, match="no hotelNo"):
        _parse_hotel([{"hotelBasicInfo": {"hotelName": "nameless"}}])


def test_hotel_with_no_plans_is_unavailable() -> None:
    hotel = _parse_hotel([{"hotelBasicInfo": BASIC}])
    assert hotel.is_available is False
    assert hotel.cheapest is None


def test_detail_blocks_are_kept() -> None:
    hotel = _parse_hotel([
        {"hotelBasicInfo": BASIC},
        {"hotelDetailInfo": {"checkinTime": "16:00", "checkoutTime": "10:00"}},
        {"hotelFacilitiesInfo": {"hotelRoomNum": 120}},
    ])
    assert hotel.detail_info["checkinTime"] == "16:00"
    assert hotel.facilities_info["hotelRoomNum"] == 120


def test_party_total_and_unit_price_are_kept_apart() -> None:
    """Live 2026-09-16: two adults, rakutenCharge 11000 per person, total 22000.

    chargeFlag describes rakutenCharge. Reading it as the unit of total is what
    labelled a two-person total as a per-person price.
    """
    charge = {"dailyCharge": {"stayDate": "2026-10-14", "rakutenCharge": 11000,
                              "total": 22000, "chargeFlag": 0}}
    plans = _parse_plans([_room(), charge])
    assert (plans[0].total, plans[0].unit_charge, plans[0].charge_flag) == (22000, 11000, 0)
