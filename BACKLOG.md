# BACKLOG.md — travel-planner

Deferred ideas, ranked roughly by when they might surface. Phase 1 is the map feature only; everything here is post-phase-1 unless explicitly pulled into a milestone.

## Phase 1 carry-overs (revisit at M5 / M7)

- **KML/KMZ output alongside CSV** — richer pins, day-grouped folders, opens in Google Earth + Maps mobile. Decision pending M1 research agent A's report.
- **Per-place "Save to Google Maps" deeplinks** (`output/saveable-places.md`) — one tap to star a place in mobile Maps. Decision pending M1 research.
- **Multi-location days** — Day 8 traverses Nagoya → Hikone → Tsumago. Default rule for now: `day.location` = where the night is spent. Revisit if it bites in M6.
- **Re-import workflow** — when the CSV changes, the user re-imports manually. Document the delete-old-map-then-reimport flow in `trips/<slug>/output/README.md` at M5.

## Phase 2 candidates

- Souvenir tracking as a queryable view over `place.tags = "souvenir-source"`.
- Budget reconciliation: structured `actual_amount_kr` per category.
- Booking status as `place.tags` lifecycle: `booking-needed` → `booking-requested` → `booking-confirmed`.
- Anthropic Maps MCP server integration for in-Claude lookups.
- Global places (place rows with `trip_id IS NULL`) — promote on explicit user request.
- Light agentic itinerary suggestions (e.g. "Claude, fill out Day 4 morning") via a `tp suggest` command that emits markdown.

## Future phases (per CLAUDE.md)

- Traveler profile + personality questionnaire.
- Vibes-based trip recommendation.
- Calendar (Google Calendar) integration.
- Tabelog + booking integrations.
- Email drafting for minshuku / restaurants.
- Cross-trip queries ("all unbooked dinners ever").

## Phase 1 post-mortem (to fill at M7)

- What was harder than expected.
- What we cut and why.
- What the M1 research agents got right vs needed correcting empirically.
