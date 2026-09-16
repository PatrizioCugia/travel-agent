# CLAUDE.md — travel-planner

This is Patrizio’s personal, Markdown-native Japan trip planner. Claude Code is
the primary interface. Read this file before working on a trip or changing the
planning system.

## Current shape

Phase 1 (Markdown → SQLite → map artifacts) and Phase 2 (Rakuten/Google
research through MCP) are shipped. The product is not a CLI: Python services
and the CLI are internal plumbing; Claude Code operates them through the
project-scoped `tp` MCP server declared in `.mcp.json`.

```text
trips/*.md + places.yaml  canonical planning record
shortlist.yaml            reversible research candidates
SQLite                    regenerable planning index
observations.db           non-regenerable availability history
MCP                       Claude Code capability surface
CLI                       maintenance, local tests, scheduled jobs
```

Never save planning state only in SQLite. `sync_trip` may rebuild a trip’s
index at any time; Markdown and Git preserve the decisions.

## Claude Code operating protocol

1. Start by reading the relevant `trip.md`, `places.yaml`, and day files, or
   use `trip_overview`.
2. Use discovery tools to research places. Their output is evidence, not a
   recommendation or a commitment.
3. Put plausible options in `shortlist.yaml`; do not put a large result set in
   `places.yaml`.
4. Promote a candidate only when Patrizio has chosen it. Promotion preserves
   stable provider IDs and URLs but drops transient search evidence.
5. After Markdown changes, run `validate_trip`. Use `sync_trip` when the
   SQLite index or map needs refreshing, then `generate_trip_map` when the
   artifacts are wanted.
6. Explain uncertainty: opening hours, restaurant quality, availability, and
   public-transit conditions can change after a tool call.

The agent may edit the repository and use read-only APIs within this workflow.
It must never book rooms, reserve restaurants, send email, or change an
external service without Patrizio’s explicit instruction.

## MCP capabilities

Use the tool that matches the question instead of a generic search:

| Question | MCP capability |
| --- | --- |
| What is currently planned? | `trip_overview`, `validate_trip` |
| Find bookable accommodation for dates | `find_lodging`, `resolve_inn`, `check_availability`, `booking_route`, `lodging_detail` |
| Find food | `find_food` |
| Find nearby onsen, ryokan candidates, minshuku, temple lodgings, or sights | `discover_nearby` |
| Check tattoo, day-use, or private-bath access for a named bath | `bathing_access` |
| Keep/review/commit candidates | `shortlist_show`, `shortlist_add_*`, `shortlist_promote` |
| Keep an eye on an unopened Ryokan calendar | `watch_add`, `watch_news` |
| Rebuild map artifacts | `sync_trip`, `generate_trip_map` |

Tool output should be compact and decision-ready. Return provider URLs rather
than raw JSON or copied reviews. A user-facing response should say what source
produced the evidence and what remains unverified.

## Source routing

Each provider has a distinct job. Do not query every provider for every
request.

- **Japanese-first identity and inventory** — retain the Japanese facility
  name, address, and local service terms as the canonical search identity.
  Resolve an inn or bath using Japanese terms when available, then check the
  Japanese OTA channels and the operator's Japanese site before considering an
  English-language aggregator. English names and pages are conveniences; they
  are never evidence that the domestic inventory or policy has been exhausted.
- **Rakuten Travel** is for Japanese lodging listings, facility information,
  and date-specific availability. An empty result can mean sold out, a
  calendar that has not opened, or no plan inventory supplied to Rakuten; it
  is never proof of any one of those states. A Rakuten price is the whole
  party's total for the first night only, and `max_yen` caps that same total.
- **Booking-route registry** (`data/booking_routes.yaml`) holds reviewed,
  stable alternate IDs and official booking/contact paths. Run
  `check_availability` first, then `booking_route` if Rakuten is empty. A
  route is evidence of where to check or contact; it is never an availability
  claim and the planner must not submit a booking or enquiry.
- **Jalan Web Service** documents an availability API and date-specific booking
  redirects for its own channel, including a stock field. New API-key
  registrations are closed, so use it only with a pre-existing sanctioned key.
  It is a secondary channel, not total inn inventory and not a booking or
  messaging API. Without a key, route the traveller to the reviewed Jalan page.
- **Google Places** resolves free-form place names, confirms canonical map
  entities, and searches restaurants. Use narrow field masks and the existing
  cache.
- **OpenStreetMap** discovers nearby public baths/onsens, accommodation,
  sights, temples, museums, viewpoints, and parks. Use it for small,
  interactive, bounded queries; cache candidates; attribute OSM/ODbL in any
  surfaced data. Do not bulk-harvest public services.
- **Bathing-access registry** (`data/bathing_access.yaml`) is a conservative
  overlay for tattoo, day-use, and private-bath policies. Policies are local:
  never infer one from OSM tags, reviews, a nearby bath, or a town name. Trust
  a current operator statement first, then an official destination or municipal
  authority. Tattoo-specific directories are discovery leads; confirm the
  operator before visiting when admission matters. A missing record means
  `unknown`, never `prohibited`.
- **Official Japanese bath directories** (`data/bathing_directories.yaml`) are
  a reviewed fallback when OSM omits a named public bath. For an exact matched
  Japanese town or bath, `discover_nearby(..., "onsen")` returns the official
  directory first, including a conservative day-use state. `listed` means an
  official schedule is published, not that the bath is open right now. Use
  `bathing_access` separately for tattoo-policy evidence.
- **Japan Search, Wikidata, and municipal open data** are future enrichment
  adapters. Use them for cultural context, official local facilities, and
  events, not as a replacement for time-sensitive availability.
- **Tabelog** has no active public API that this project can depend on. Never
  scrape it. Google results may carry a Tabelog search link for Patrizio to
  inspect manually; do not copy ratings or reviews into project data.

External candidates retain `source_refs` (for example, an OSM object ID) and
source URLs after promotion. Raw provider response bodies never enter trip
Markdown.

## Routing and itineraries

Use generated Google Maps URLs as the final phone-navigation handoff. Do not
automatically reorder days or treat a map route as an itinerary decision.

`check_day_feasibility` evaluates consecutive committed stops, as currently
written in the day Markdown, with straight-line gaps and per-leg Google Maps
handoffs. It reports no timetable or duration as fact. Transit data is live
evidence: never calculate it during parsing or discovery, and do not overwrite
day Markdown with a computed route.

## Traveller preferences

Patrizio and his sister travel slowly and food-first. The aim is a few singular
experiences, not maximum coverage.

- In the countryside, prefer family-run minshuku or ryokan with dinner and
  breakfast; the meal is part of the stay.
- In cities, value location and low friction over a hotel experience.
- Avoid redundancy: a trip needs one excellent kaiseki/ryokan dinner, not four
  versions of it.
- Treat small-inn review counts cautiously, and label all Google restaurant
  ratings as Google’s rather than Japanese local consensus.

The detailed lodging judgement layer lives in `.claude/skills/japan-lodging`.
Keep taste in the agent instructions, not hard-coded ranking rules, so a
practical option remains visible when it is right for the trip.

## Repository conventions

- `places.yaml` is the structured source of truth. IDs are stable lowercase
  kebab-case and day prose references them as `[[place-id]]`.
- `shortlist.yaml` mirrors a place entry plus `_found` evidence. Promotion is a
  move, not a retyped copy.
- `data/travel_planner.db` is safe to recreate. `data/observations.db` stores
  watch history and must survive parsing.
- Generated files under `trips/*/output/` are disposable. Regenerate them;
  never edit them by hand.
- All external writes remain manual: Google My Maps import, bookings, contact
  forms, and restaurant reservations.

## Development

Keep provider adapters separate from MCP orchestration. Provider code returns
typed, normalized data; MCP owns compact rendering and the decision workflow.
Add a test for each parser, source normalizer, or state transition. Run the
relevant test slice first, then the full suite and static checks after a
cross-cutting change.
