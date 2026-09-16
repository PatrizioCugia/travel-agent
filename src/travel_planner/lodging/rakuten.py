"""Rakuten Travel API client for the `tp` travel planner.

Covers the three endpoints that matter for trip planning:

  VacantHotelSearch   real-time availability          <- the one that matters
  KeywordHotelSearch  inn name -> hotelNo
  GetAreaClass        the largeClass/middleClass/... area code tree

Gotchas this module handles for you, every one of which will otherwise
silently ruin an afternoon:

  1. `accessKey` is now REQUIRED alongside `applicationId`. It is marked
     [NEW] in the docs and essentially every Qiita post and GitHub sample
     predates it. Without it you get a bare 400 wrong_parameter.
  2. Coordinates DEFAULT to Tokyo Datum in ARC-SECONDS (Tokyo Station is
     latitude=128440.51). We always send datumType=1 to work in WGS84
     decimal degrees on both input and output.
  3. searchRadius is capped at 3.0 km. Not 30. Three. And min 0.1.
  4. HTTP 404 `not_found` is a legitimate "nothing returned by this channel"
     answer, not an error. It can mean sold out, a calendar not yet published,
     or that the property has no Rakuten plan inventory, so we return an empty
     result instead of making up a cause.
  5. hotelMinCharge, lowestCharge and highestCharge are dead fields that
     always return 0. Use dailyCharge.total.
  6. dailyCharge only covers the FIRST night of a multi-night stay.
     dailyCharge.total is the whole party's price for that night (every adult,
     every room). chargeFlag describes rakutenCharge — the plan's unit price,
     per person (0) or per room (1) — never total. maxCharge/minCharge filter
     on total. Verified live 2026-09-16: 2 adults, rakutenCharge 11000,
     chargeFlag 0, total 22000; 4 adults in 2 rooms, 5800 → 23200. The one
     unsettled case is a per-room plan (chargeFlag 1) booked as several
     rooms: a single sample showed total equal to one room's price.
  7. You cannot get a room count. reserveRecordCount is a count of
     bookable *plans*, not rooms. Do not build inventory logic on it.
  8. The app is IP-allowlisted (API/backend type). Our address is a dynamic
     residential lease, so a working setup breaks by itself when the ISP
     rotates it, when a VPN is on, and while travelling. A rejection names
     the allowlist explicitly rather than echoing Rakuten's bare body —
     `tp doctor` prints the current public IP to compare.

Env: RAKUTEN_APP_ID, RAKUTEN_ACCESS_KEY  (optional RAKUTEN_AFFILIATE_ID)
"""

from __future__ import annotations

import os
import time
import urllib.parse
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

import httpx

BASE = "https://openapi.rakuten.co.jp/engine/api/Travel"

VACANT = f"{BASE}/VacantHotelSearch/20170426"
KEYWORD = f"{BASE}/KeywordHotelSearch/20260731"
DETAIL = f"{BASE}/HotelDetailSearch/20260731"
AREA_CLASS = f"{BASE}/GetAreaClass/20131024"

# squeezeCondition values, per the docs. Combine with commas.
SqueezeCondition = Literal[
    "kinen",      # non-smoking room
    "internet",   # in-room internet
    "daiyoku",    # large communal bath
    "onsen",      # hot spring
    "breakfast",  # breakfast included
    "dinner",     # dinner included
]


class RakutenError(RuntimeError):
    """Non-recoverable API error (bad params, auth, or a 5xx that stuck)."""


@dataclass(frozen=True)
class Plan:
    """One bookable room/plan combination on one night."""

    room_name: str
    plan_name: str
    plan_id: str | None
    total: int | None          # yen, first night, whole party (all adults, all rooms)
    charge_flag: int | None    # unit of unit_charge: 0 = per person, 1 = per room
    unit_charge: int | None    # rakutenCharge: first night, one person or one room
    with_dinner: bool
    with_breakfast: bool
    reserve_url: str | None

    @property
    def fingerprint(self) -> str:
        """Stable identity for diffing across polls.

        Deliberately excludes price so that a price change surfaces as a
        change to an existing plan rather than as a new plan appearing.
        """
        return f"{self.room_name}|{self.plan_name}|{self.plan_id or ''}"


@dataclass(frozen=True)
class Hotel:
    hotel_no: int
    name: str
    kana: str | None
    lat: float | None          # WGS84 degrees (datumType=1)
    lng: float | None
    address: str
    telephone: str | None
    nearest_station: str | None
    info_url: str | None
    plan_list_url: str | None
    review_average: float | None
    review_count: int | None
    special: str | None = None                     # hotelSpecial blurb, Japanese
    plans: list[Plan] = field(default_factory=list)
    # Only populated by detail(); responseType=large carries these.
    detail_info: dict[str, Any] = field(default_factory=dict)
    facilities_info: dict[str, Any] = field(default_factory=dict)

    @property
    def is_available(self) -> bool:
        return bool(self.plans)

    @property
    def page_url(self) -> str:
        """The canonical Rakuten page for this inn.

        planListUrl comes back as a 200-character affiliate redirect through
        hb.afl.rakuten.co.jp, which is unreadable in a terminal and unpleasant
        to paste. This is the URL a human actually wants.
        """
        return f"https://travel.rakuten.co.jp/HOTEL/{self.hotel_no}/{self.hotel_no}.html"

    @property
    def cheapest(self) -> Plan | None:
        priced = [p for p in self.plans if p.total is not None]
        return min(priced, key=lambda p: p.total or 0) if priced else None


class RakutenTravel:
    def __init__(
        self,
        app_id: str | None = None,
        access_key: str | None = None,
        affiliate_id: str | None = None,
        *,
        timeout: float = 20.0,
        min_interval: float = 1.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.app_id = app_id or os.environ.get("RAKUTEN_APP_ID", "")
        self.access_key = access_key or os.environ.get("RAKUTEN_ACCESS_KEY", "")
        self.affiliate_id = affiliate_id or os.environ.get("RAKUTEN_AFFILIATE_ID")
        if not self.app_id or not self.access_key:
            raise RakutenError(
                "Set RAKUTEN_APP_ID and RAKUTEN_ACCESS_KEY. Both are required "
                "since the accessKey change; app_id alone returns 400."
            )
        self._client = client or httpx.Client(timeout=timeout)
        self._min_interval = min_interval
        self._last_call = 0.0

    # ---------------------------------------------------------------- core

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Return parsed JSON, or None for a legitimate 'no results' 404."""
        # Rakuten throttles aggressively on repeated identical URLs.
        gap = time.monotonic() - self._last_call
        if gap < self._min_interval:
            time.sleep(self._min_interval - gap)

        params = {
            "applicationId": self.app_id,
            "accessKey": self.access_key,
            "format": "json",
            "formatVersion": 2,
            **{k: v for k, v in params.items() if v is not None},
        }
        if self.affiliate_id:
            params["affiliateId"] = self.affiliate_id

        for attempt in range(4):
            r = self._client.get(url, params=params)
            self._last_call = time.monotonic()

            if r.status_code == 404:
                return None                      # no availability, not an error
            if r.status_code in (429, 503):
                time.sleep(2 ** attempt * 5)     # 5s, 10s, 20s
                continue
            if r.status_code in (400, 401, 403):
                raise RakutenError(_auth_hint(r.status_code, r.text[:400]))
            if r.status_code >= 400:
                body = r.text[:400]
                raise RakutenError(f"{r.status_code} from {url}: {body}")
            data: dict[str, Any] = r.json()
            return data

        raise RakutenError(f"Rate limited or unavailable after 4 attempts: {url}")

    # ------------------------------------------------------------ vacancy

    def vacancy(
        self,
        checkin: date,
        checkout: date,
        *,
        hotel_nos: Iterable[int] | None = None,
        lat: float | None = None,
        lng: float | None = None,
        radius_km: float = 1.0,
        large: str | None = None,
        middle: str | None = None,
        small: str | None = None,
        detail: str | None = None,
        adults: int = 2,
        rooms: int = 1,
        max_charge: int | None = None,
        min_charge: int | None = None,
        squeeze: Iterable[SqueezeCondition] | None = None,
        sort: str = "standard",
        hits: int = 30,
        page: int = 1,
    ) -> list[Hotel]:
        """Real-time availability.

        Exactly one locator is needed: hotel_nos, lat/lng, or area codes.
        Precedence if you pass several is hotelNo > lat/lng > area codes.

        hotel_nos is capped at 15 per call by the API; we chunk for you.
        """
        if hotel_nos is not None:
            hotel_nos = list(hotel_nos)
            out: list[Hotel] = []
            for i in range(0, len(hotel_nos), 15):
                out.extend(
                    self._vacancy_call(
                        checkin, checkout,
                        hotel_no=",".join(str(n) for n in hotel_nos[i:i + 15]),
                        adults=adults, rooms=rooms,
                        max_charge=max_charge, min_charge=min_charge,
                        squeeze=squeeze, sort=sort, hits=hits, page=page,
                    )
                )
            return out

        if lat is not None and lng is not None:
            if not 0.1 <= radius_km <= 3.0:
                raise ValueError("searchRadius must be between 0.1 and 3.0 km")
            return self._vacancy_call(
                checkin, checkout, latitude=lat, longitude=lng,
                search_radius=radius_km, adults=adults, rooms=rooms,
                max_charge=max_charge, min_charge=min_charge,
                squeeze=squeeze, sort=sort, hits=hits, page=page,
            )

        if not large:
            raise ValueError("Pass hotel_nos, lat/lng, or at least largeClassCode")
        return self._vacancy_call(
            checkin, checkout,
            large_class_code=large, middle_class_code=middle,
            small_class_code=small, detail_class_code=detail,
            adults=adults, rooms=rooms,
            max_charge=max_charge, min_charge=min_charge,
            squeeze=squeeze, sort=sort, hits=hits, page=page,
        )

    def _vacancy_call(
        self,
        checkin: date,
        checkout: date,
        *,
        hotel_no: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        search_radius: float | None = None,
        large_class_code: str | None = None,
        middle_class_code: str | None = None,
        small_class_code: str | None = None,
        detail_class_code: str | None = None,
        adults: int,
        rooms: int,
        max_charge: int | None,
        min_charge: int | None,
        squeeze: Iterable[SqueezeCondition] | None,
        sort: str,
        hits: int,
        page: int,
    ) -> list[Hotel]:
        data = self._get(
            VACANT,
            {
                "checkinDate": checkin.isoformat(),
                "checkoutDate": checkout.isoformat(),
                "hotelNo": hotel_no,
                "latitude": latitude,
                "longitude": longitude,
                "searchRadius": search_radius,
                "largeClassCode": large_class_code,
                "middleClassCode": middle_class_code,
                "smallClassCode": small_class_code,
                "detailClassCode": detail_class_code,
                "adultNum": adults,
                "roomNum": rooms,
                "maxCharge": max_charge,
                "minCharge": min_charge,
                "squeezeCondition": ",".join(squeeze) if squeeze else None,
                "datumType": 1,          # WGS84 degrees. Never omit this.
                "searchPattern": 0,      # per facility, up to 3 plans each
                "responseType": "middle",
                "sort": sort,
                "hits": min(hits, 30),
                "page": page,
            },
        )
        if data is None:
            return []
        return [_parse_hotel(h) for h in data.get("hotels", [])]

    # ------------------------------------------------------------ lookup

    def resolve(self, keyword: str, *, hits: int = 10) -> list[Hotel]:
        """Resolve an inn name to a hotelNo. Japanese name works far better
        than romaji: '湯原温泉 湯本荘' will hit, 'Yubara Onsen Yumotoso' may not.
        """
        data = self._get(KEYWORD, {"keyword": keyword, "datumType": 1,
                                   "hits": min(hits, 30), "responseType": "middle"})
        if data is None:
            return []
        return [_parse_hotel(h) for h in data.get("hotels", [])]

    def detail(self, hotel_no: int) -> Hotel | None:
        """Facility detail: check-in/out times, bath and facility info.

        responseType=large is what carries hotelDetailInfo and
        hotelFacilitiesInfo; middle omits both entirely.
        """
        data = self._get(
            DETAIL,
            {"hotelNo": hotel_no, "datumType": 1, "responseType": "large"},
        )
        if data is None:
            return None
        hotels = data.get("hotels", [])
        return _parse_hotel(hotels[0]) if hotels else None

    def area_class(self) -> dict[str, Any]:
        """The full area code tree. Cache this; it changes maybe yearly.

        Note the docs' rule: if a class has children you MUST descend to the
        leaf. largeClassCode=japan alone is rejected.
        """
        data = self._get(AREA_CLASS, {})
        return data or {}


# ------------------------------------------------------------------ parsing

def _flatten(entries: Any) -> list[dict[str, Any]]:
    """roomInfo arrives either flat or nested one level. Handle both."""
    out: list[dict[str, Any]] = []
    for entry in entries or []:
        if isinstance(entry, list):
            out.extend(e for e in entry if isinstance(e, dict))
        elif isinstance(entry, dict):
            out.append(entry)
    return out


def _parse_plans(room_info: Any) -> list[Plan]:
    """Pair each roomBasicInfo with the dailyCharge that follows it.

    Live responses put these side by side in ONE flat list —
    [{roomBasicInfo}, {dailyCharge}] — rather than nesting a list per plan.
    The original implementation zipped each element against itself, so the
    charge block never met its room block and EVERY price came back None.
    Streaming the list and attaching each charge to the most recent room is
    correct for the flat shape and still correct if Rakuten ever nests.
    """
    plans: list[Plan] = []
    room: dict[str, Any] | None = None
    charge: dict[str, Any] = {}

    def flush() -> None:
        nonlocal room, charge
        if room is None:
            return
        plans.append(
            Plan(
                room_name=room.get("roomName", ""),
                plan_name=room.get("planName", ""),
                plan_id=str(room["planId"]) if room.get("planId") else None,
                total=charge.get("total"),
                charge_flag=charge.get("chargeFlag"),
                unit_charge=charge.get("rakutenCharge"),
                with_dinner=bool(room.get("withDinnerFlag")),
                with_breakfast=bool(room.get("withBreakfastFlag")),
                reserve_url=_unwrap_affiliate(room.get("reserveUrl")),
            )
        )
        room, charge = None, {}

    for entry in _flatten(room_info):
        if "roomBasicInfo" in entry:
            flush()                                   # previous plan is complete
            room = entry["roomBasicInfo"] or {}
        elif "dailyCharge" in entry:
            charge = entry["dailyCharge"] or {}
    flush()
    return plans


def _parse_hotel(raw: Any) -> Hotel:
    """formatVersion=2 still nests as [{hotelBasicInfo}, {roomInfo: [...]}]."""
    blocks = raw if isinstance(raw, list) else [raw]

    basic: dict[str, Any] = {}
    detail_info: dict[str, Any] = {}
    facilities_info: dict[str, Any] = {}
    plans: list[Plan] = []

    for block in blocks:
        if not isinstance(block, dict):
            continue
        if "hotelBasicInfo" in block:
            basic = block["hotelBasicInfo"]
        if "hotelDetailInfo" in block:
            detail_info = block["hotelDetailInfo"] or {}
        if "hotelFacilitiesInfo" in block:
            facilities_info = block["hotelFacilitiesInfo"] or {}
        if block.get("roomInfo"):
            plans.extend(_parse_plans(block["roomInfo"]))

    if basic.get("hotelNo") in (None, ""):
        # Silently defaulting to 0 here produced rows that looked like real
        # hotels and could never be re-queried. Fail where the problem is.
        raise RakutenError(f"Rakuten returned a hotel block with no hotelNo: {str(raw)[:200]}")

    return Hotel(
        hotel_no=int(basic["hotelNo"]),
        name=basic.get("hotelName", ""),
        kana=basic.get("hotelKanaName"),
        lat=basic.get("latitude"),      # degrees, because datumType=1
        lng=basic.get("longitude"),
        address=f"{basic.get('address1', '')}{basic.get('address2', '')}",
        telephone=basic.get("telephoneNo"),
        nearest_station=basic.get("nearestStation"),
        info_url=basic.get("hotelInformationUrl"),
        plan_list_url=basic.get("planListUrl"),
        review_average=basic.get("reviewAverage"),
        review_count=basic.get("reviewCount"),
        special=basic.get("hotelSpecial"),
        plans=plans,
        detail_info=detail_info,
        facilities_info=facilities_info,
    )


def _unwrap_affiliate(url: str | None) -> str | None:
    """Strip Rakuten's affiliate redirect wrapper off a URL.

    Reserve links come back as 250-character hb.afl.rakuten.co.jp redirects
    with the real destination sitting url-encoded in the `pc` parameter, even
    with no affiliate ID configured. Unusable in a terminal, and nobody wants
    to paste one. The real URL works on its own.
    """
    if not url or "hb.afl.rakuten.co.jp" not in url:
        return url
    inner = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("pc")
    return inner[0] if inner else url


def _auth_hint(status: int, body: str) -> str:
    """Rakuten's 4xx bodies say almost nothing. Say what actually goes wrong."""
    causes = [
        "accessKey missing or mistyped — applicationId alone always returns 400",
        "app ID and access key belonging to different applications",
        "the app's IP allowlist not matching your current public IP "
        "(dynamic ISP lease, VPN on, or you are travelling) — run `tp doctor`",
        "a stray space or quote pasted into .env",
    ]
    bullets = "\n".join(f"    - {c}" for c in causes)
    return f"{status} from Rakuten: {body}\n\n  Usual causes:\n{bullets}"
