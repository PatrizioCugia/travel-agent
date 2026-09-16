# BACKLOG.md — travel-planner

Deferred ideas, ranked roughly by when they might surface. Phase 1 (the map feature) shipped in M7. Phase 2 (the lodging/food research layer) shipped after it — see the phase-2 notes at the bottom.

## Deferred from phase 2

- **Notification channel.** Watch findings currently sit in `tp watch log` until asked for. Push (Telegram/email/macOS notification) was deliberately deferred — revisit if a calendar opens and closes between two check-ins.
- **Travelling breaks the watcher.** The Rakuten app is IP-allowlisted to a home ISP lease; the nightly run fails from anywhere else, including Japan. Options: an always-on host, or a broader allowlist entry.
- **Map visualizer upgrade** (GSI tiles, availability-coloured pins). Explicitly out of phase 2.
- **`booking_status` as a derived view.** Implemented as tags for now (`booking-needed`), per the phase-1 convention. A view joining `place` to the latest snapshot would let `tp` answer "you said you need to book this, and it is bookable at ¥X" — not yet built.
- **Area-code search path.** `GetAreaClass` is wired in the client but unused: all searching goes through geocode → lat/lng, which is capped at a 3 km radius. Region-wide searches ("anywhere in Hida") need the area tree.
- **English names for Rakuten inns are best-effort.** `shortlist_add_lodging` geocodes the Japanese name through Places and takes the English display name if the match is within 2 km. When it misses, the slug falls back to `rakuten-<hotelNo>`. Google's English names also sometimes carry kanji inline (`Kamameshi Shizuka Kouen-ten志津香`), which lands in `name_en` and wants hand-editing.
- **`tp watch log` piped to `head` still marks everything seen.** Use `--keep-unseen` when skimming.

## Immediate carry-overs from M6

- **17 Nagoya places with low-confidence lookup matches** — listed in `trips/nagoya-2026-11/output/lookup-misses.md`. Resolve by either tightening the name/address in `places.yaml` and re-running `tp parse nagoya`, or pasting a manually-looked-up `google_place_id` + lat/lng directly into `places.yaml`. Mostly generic names (`wakashachiya`, `konparu-kissaten`) or placeholder addresses (`seki-local-lunch`).
- **Spot-check the 56 confidently-matched pins in My Maps after the first import**. The distance gate caught the worst regional mismatches, but it's worth one walk-through of the pins in the actual Nagoya/Tsumago/Okuhida layers.

## Lookup-accuracy improvements (post phase 1)

- **Verify-then-trust pass**: after lookup, compare each match's `formattedAddress` against the place's expected city/prefecture and surface anything where the prefecture differs as a soft warning, not a hard miss.
- **Tighter location bias radius** for places with very specific addresses (street level) — currently 25 km is generous.
- **Manual override list** in `places.yaml` for known-tricky places: a `_lookup_force: { place_id: ChIJ... }` block that skips the API entirely.

## Phase 2 candidates

- Souvenir tracking as a queryable view over `place.tags = "souvenir-source"`.
- Budget reconciliation: structured `actual_amount_kr` per category.
- Booking-status lifecycle on `place.tags`: `booking-needed` → `booking-requested` → `booking-confirmed`.
- Anthropic Maps MCP server integration for in-Claude lookups.
- Global places (place rows with `trip_id IS NULL`) — promote on explicit user request.
- Light agentic itinerary suggestions (`tp suggest` command emitting markdown drafts).
- Time-slot inference from `## Morning` / `## Lunch` headings in day prose → `day_place.time_slot`.

## Future phases (per CLAUDE.md)

- Traveler profile + personality questionnaire.
- Vibes-based trip recommendation.
- Calendar (Google Calendar) integration.
- Tabelog + booking integrations.
- Email drafting for minshuku / restaurants.
- Cross-trip queries ("all unbooked dinners ever").

## Phase 1 post-mortem

### What worked

- **Plan-first session pattern**. The Step-1-through-6 plan in `PLAN.md` shaped every subsequent milestone and made it easy to push back on scope creep mid-flight (KML, saveable-places stayed scoped to M5 instead of sprawling).
- **M1 research agents caught a load-bearing fact** the day before we wrote the spike: legacy Places API is closed to new projects since 2024. Without that, the spike code (and possibly M3) would have been built against the wrong endpoint.
- **3-Opus-agent migration in M6** produced day-file prose with consistent voice and accurate slug references across 12 days. Splitting by location (Nagoya / Hikone+Tsumago / Okuhida) was the right boundary — themes shift naturally with geography.
- **Markdown-canonical / DB-regenerable architecture** kept iteration cheap. Schema changes (`theme` → `title`, slug regex relax) were one-line edits with no migration.
- **Live spike in M1** caught the Places API enablement gap before M3 was committed. The diagnostic checklist in the spike command paid off on first error.

### What was harder than expected

- **Places API scoring under real Japanese place data**. Two iterations were needed: (a) rebalance reviews/operational vs. address overlap so famous places with kanji-only `formattedAddress` don't fail on token mismatch with romaji target; (b) per-address region bias + 50 km distance gate to keep "Maruya in Tsumago" from matching "Maruya somewhere in Nagoya" with a high review count. Real-world test in M6 exposed this — unit tests wouldn't have.
- **YAML round-trip with ruamel** needed explicit `indent(mapping=2, sequence=2, offset=0)` to preserve the canonical `- ` list style. Defaults re-indent every item to column 2 — disrupted Patrizio's input formatting on first run.
- **Python 3.14 + pydantic** flagged a field name (`date: date | None = None` in `DayFrontmatter`) that shadowed the imported `datetime.date` type during annotation evaluation. Renamed the import to `date_t`. Older Python versions tolerate the shadow.
- **The misleading `api_calls` counter** in the enrichment report — I named it for HTTP calls but it counted successful matches, so the first live run reported "0 API calls, 1 miss" when the API was hit 4 times for that one place. Renamed to `new_matches` and adjusted the message format.

### What we cut and why

- **Time-slot inference from prose headings** (`## Lunch` → `day_place.time_slot: lunch`) was originally penciled in for M4 then M5. Deferred — the daily-routes URL works without it, and inference rules add fragility for marginal value. Moved to phase 2.
- **Region category and `role` column on day_place** were cut early (during plan refinement) when the schema-overkill pushback landed. Backups/alternates became unattached places with `tag: backup`; regions became `day.location` strings.

### What the M1 research agents got right vs needed correcting

- ✅ **Got right**: Places API (New) endpoint shape, field-mask cost tiers, CSV column ordering, the `?api=1&query_place_id=` deeplink form, KML being worth emitting alongside CSV, ruamel for round-trip.
- ⚠️ **Needed correction**: agent B's scoring recipe (token overlap on address) assumed both addresses in the same script — failed when API returns Japanese and our addresses are romaji. Empirical fix landed in M3. Also: agent B underweighted the importance of a per-place region bias for multi-region trips; M6 caught it.

### Numbers

- **8 commits** on `main`, ~5,000 lines of code + tests + trip content.
- **100 tests** passing through every milestone, ruff + mypy --strict clean.
- **73 places, 12 days, 77 day-place links** synced from markdown to SQLite for Nagoya 2026.
- **56/73 places (77%)** matched at high confidence with correct region on first live lookup; 17 went to `lookup-misses.md` for manual review.
- **4 parallel Opus agents** in M6 produced the trip content in ~3 minutes wall-clock.


## Phase 2 post-mortem

### What worked

- **Reference modules as a starting point, read critically.** `rakuten.py` arrived with nine hard-won API gotchas, every one of which held up against the live docs and live traffic. Keeping its substance and rewriting only what was demonstrably wrong was the right call — the alternative (rewrite from scratch) would have re-lost a day to `accessKey` and `datumType`.
- **Answering the durability question structurally.** Two database files ended the argument: `tp parse` cascade-deletes a trip, so observational data in the planning DB is either destroyed or lying about its foreign key. No rule to remember.
- **Date windows as a first-class concept.** Dates weren't locked, so `--window A..B --nights N` expands to one target per candidate check-in. Batching by date meant 31 targets cost 18 API calls, not 31.
- **Using the thing before declaring it done.** Three real defects only appeared in live use: every price parsed as `None`, reserve URLs came back as 250-character affiliate redirects, and `find_food` didn't print the place id its own shortlist tool needs.

### What was harder than expected

- **The reference parser dropped every price.** `roomInfo` arrives as ONE flat list — `[{roomBasicInfo}, {dailyCharge}]` — and the original code zipped each element against itself, so the charge block never met its room block. Caught only because a live search showed "price n/a" on every row. Unit tests written against an assumed shape would have passed happily.
- **`mcp` 2.0 moved the API.** `mcp.server.fastmcp.FastMCP` is gone; it is `mcp.server.MCPServer` now, with the same decorator shape. Every tutorial and the reference module predate it.
- **Importing `mcp` leaked API keys into logs.** It installs a logging handler that makes httpx's INFO request logging visible, and Rakuten authenticates by query string — so both credentials printed in full, and would have been written to `data/watch.log` on every scheduled run. Fixed in `logging_setup.py`. The keys printed during development are compromised and need regenerating at https://webservice.rakuten.co.jp/app/list — the IP allowlist limits the damage but does not remove it.
- **Google Places `locationBias` is a hint, not a boundary.** A restaurant search near Tōdai-ji cheerfully returned a place 30 km away in Osaka. `searchText` only supports rectangular `locationRestriction`, so results are distance-gated client-side at twice the requested radius.
- **Rakuten's IP allowlist on API/backend apps** is not in any of the tutorials, and pins the whole thing to a dynamic residential address.

### Numbers

- **13 MCP tools**, 5 CLI command groups, 2 databases.
- **151 tests** (100 carried from phase 1, 51 new), ruff + `mypy --strict` clean.
- **31 watch targets** across the Omizutori fortnight polled in 29 s (18 API calls at the 1 QPS floor).
- **3 defects found by live use** that no unit test written from the docs would have caught.
