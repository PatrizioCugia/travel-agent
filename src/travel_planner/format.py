"""Output shaping. One place, so the CLI and the MCP server never drift.

House style, per Patrizio's map-CSV preference: Western-script name first,
Japanese name alongside, short English description. Rakuten only ever returns
Japanese names, so lodging search results lead with the Japanese name until a
place is promoted to the shortlist, at which point a Places lookup supplies
the English one.
"""

from __future__ import annotations

import os


def yen(amount: int | None) -> str:
    return f"¥{amount:,}" if amount is not None else "price n/a"


def _rate() -> float | None:
    """Yen per 1 DKK, from .env. Display only; deliberately hand-maintained."""
    raw = os.environ.get("JPY_PER_DKK", "").strip()
    if not raw:
        return None
    try:
        rate = float(raw)
    except ValueError:
        return None
    return rate if rate > 0 else None


def yen_kr(amount: int | None) -> str:
    """'¥38,000 (~1,530 kr)', or just the yen if no rate is configured."""
    if amount is None:
        return "price n/a"
    rate = _rate()
    if rate is None:
        return yen(amount)
    return f"{yen(amount)} (~{round(amount / rate):,} kr)"


def meals(with_dinner: bool, with_breakfast: bool) -> str:
    """Japanese shorthand, as it appears on Rakuten itself: 夕 dinner, 朝 breakfast."""
    return ("夕" if with_dinner else "") + ("朝" if with_breakfast else "")


def meals_en(with_dinner: bool, with_breakfast: bool) -> str:
    if with_dinner and with_breakfast:
        return "half board"
    if with_dinner:
        return "dinner"
    if with_breakfast:
        return "breakfast"
    return "room only"


def name_line(name_en: str | None, name_local: str | None) -> str:
    """Western script first, Japanese alongside. Either may be missing."""
    if name_en and name_local and name_en != name_local:
        return f"{name_en} {name_local}"
    return name_en or name_local or "(unnamed)"


def review(average: float | None, count: int | None) -> str:
    """Rakuten returns a count with no average for barely-reviewed places."""
    if not count:
        return "no reviews"
    if average is None:
        return f"{count} review(s), unrated"
    return f"{average} ({count})"


def truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
