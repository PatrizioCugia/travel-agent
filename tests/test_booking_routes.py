"""Tests for the reviewed booking-route registry and its safe rendering."""

from __future__ import annotations

from travel_planner.lodging import routes


def test_registry_covers_the_twenty_inn_research_sample() -> None:
    registry = routes.load_registry()
    assert set(registry) == {
        8108, 8766, 14567, 41857, 44984, 79381, 105973, 140962, 147963, 149148,
        151275, 153491, 177984, 183934, 184241, 184602, 187093, 187318, 188068, 195801,
    }
    assert registry[8766].channels[0].provider == "jalan"
    assert registry[8766].channels[0].external_id == "312156"
    assert registry[149148].channels[0].access == "contact"
    assert registry[79381].channels[0].provider == "official_direct"
    assert registry[79381].channels[1].external_id == "322386"


def test_render_keeps_actions_human_controlled() -> None:
    text = routes.render(187318)
    assert "Rakuten" in text
    assert "Jalan #351018" in text
    assert "APA Partner" in text
    assert "Do not submit a booking or enquiry" in text


def test_unknown_inn_is_not_assumed_unavailable() -> None:
    text = routes.render(999999)
    assert "No verified alternate route" in text
    assert "before treating it as full" in text


def test_audit_describes_routes_not_stock() -> None:
    text = routes.audit()
    assert text.startswith("20 inns")
    assert "8 Jalan identities" in text
    assert "route coverage, not availability" in text
