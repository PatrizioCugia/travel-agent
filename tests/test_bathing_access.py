"""Tests for conservative, source-linked onsen access evidence."""

from __future__ import annotations

from travel_planner.discovery import bathing


def test_official_destination_policy_matches_each_kinosaki_public_bath() -> None:
    record = bathing.find("鴻の湯")
    assert record is not None
    assert record.record_id == "kinosaki-public-baths"
    assert record.tattoo_status == "allowed"
    assert record.evidence_tier == "official_destination"
    assert record.day_use is True


def test_render_preserves_scope_and_does_not_extend_it_to_ryokan_baths() -> None:
    text = bathing.render("Kinosaki Onsen")
    assert "Tattoos of all sizes are accepted" in text
    assert "not baths inside accommodations" in text
    assert "official destination" in text.lower()


def test_unknown_policy_is_explicitly_unknown() -> None:
    text = bathing.render("Imaginary Onsen")
    assert "Status: unknown" in text
    assert "not a denial" not in text
    assert "contact the facility" in text


def test_audit_describes_deliberately_incomplete_coverage() -> None:
    text = bathing.audit()
    assert text.startswith("1 reviewed bathing-policy")
    assert "1 allowed" in text
    assert "absence from the registry means unknown" in text
