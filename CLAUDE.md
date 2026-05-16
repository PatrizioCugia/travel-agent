# CLAUDE.md — travel-planner

> Instructions for Claude (and future me) when operating inside this repo.
> Read this file fully at the start of every session. It is the source of truth for scope, conventions, and what we are NOT doing yet.

---

## What this project is

A personal travel planning system for Patrizio. Long-term: a structured planning agent that helps research, plan, book, and document trips, with strong opinions about food, craft, slow pace, and singular seasonal experiences. The agent operates on markdown files (Obsidian-native) backed by a SQLite index, with Claude Code as the primary interface.

Long-term capabilities (NOT in scope for phase 1):
- Traveler profile + personality questionnaire
- Vibes-based trip recommendation engine
- Calendar (Google Calendar) integration
- Tabelog and booking integrations
- Email drafting for minshuku/restaurants
- Cross-trip queries ("all unbooked dinners ever")
- Light agentic execution (with explicit approval per action)
- Web dashboards or any UI beyond CLI + Obsidian

**Phase 1 scope, strictly: build the map feature.**
- Parse trip markdown → structured DB
- Generate Google My Maps CSV + per-day Google Maps directions URLs
- Generate human-readable index markdown
- Selectable by name (e.g. `Nagoya-11/2026`)
- Migrate the existing Nagoya 2026 trip as v0 test case

Anything beyond this is OUT OF SCOPE until phase 1 is solid and shipped. If Patrizio asks for an out-of-scope feature mid-build, propose deferring it and writing it down in `BACKLOG.md` instead.

---

## Strong opinions baked in

These are decisions already made through sparring. Don't relitigate them unless Patrizio explicitly opens the question.

1. **SQLite + markdown hybrid.** Markdown is the human-facing source of truth. SQLite is a generated index, rebuilt by `tp parse`. Never mutate the DB directly as a way of "saving" data — markdown is canonical.
2. **No web UI.** CLI + Obsidian + Google My Maps. Anything that looks like dashboard-building is a red flag.
3. **No agentic actions in phase 1.** Pure deterministic pipeline: markdown in → files out. No emails, no API writes, no bookings. The agent's role is to read context, run scripts, edit markdown, and explain. Never to act on Patrizio's behalf in external systems.
4. **Patrizio-specific, not generic.** This system encodes his taste, savings rhythm, inn-vs-hotel split, "singular experience per trip" filter. Resist the urge to generalize for hypothetical other users.
5. **One-way map round trip.** Markdown → CSV → manual import into Google My Maps (a 30-second action). We do NOT try to write to Google's saved places (no such API exists). If a generated CSV needs re-import, the workflow is: delete old My Maps map, import the new CSV. Map URLs are stored in the DB after the first import.
6. **Honest failure analysis over polish.** When something fails (place lookup misses, parser confused, API rate-limited), report it cleanly. Don't paper over edge cases with fake confidence.

---

## Repo structure

```
~/projects/travel-planner/
├── CLAUDE.md                          # this file
├── README.md
├── BACKLOG.md                         # deferred ideas, ranked by phase
├── pyproject.toml                     # uv-managed
├── .env.example                       # GOOGLE_MAPS_API_KEY etc.
├── .env                               # gitignored, real keys
├── src/travel_planner/
│   ├── __init__.py
│   ├── schema.py                      # dataclasses + DDL strings
│   ├── parser/
│   │   ├── markdown_parser.py         # YAML places.yaml + frontmatter + prose fallback
│   │   └── frontmatter.py
│   ├── maps/
│   │   ├── places_lookup.py           # Google Places API
│   │   ├── csv_generator.py           # My Maps-compatible CSV
│   │   └── directions_url.py          # Google Maps directions URLs per day
│   ├── db/
│   │   ├── init_db.py
│   │   └── sync.py                    # markdown → DB
│   └── cli.py                         # typer entry point
├── trips/
│   ├── _template/                     # scaffold for new trips
│   ├── nagoya-2026-11/
│   │   ├── trip.md
│   │   ├── places.yaml                # canonical structured place list
│   │   ├── overview.md
│   │   ├── days/
│   │   │   ├── day-01.md
│   │   │   └── ...
│   │   ├── food.md
│   │   ├── restaurants.md
│   │   ├── phrases.md
│   │   ├── late-night-food.md
│   │   └── output/
│   │       ├── my-maps.csv            # generated
│   │       ├── daily-routes.md        # generated
│   │       └── places-index.md        # generated
├── data/
│   └── travel_planner.db              # gitignored
└── tests/
    ├── test_parser.py
    ├── test_places_lookup.py
    └── test_csv_generator.py
```

---

## Data schema (v0)

Defined in `src/travel_planner/schema.py`. Tables:

- **trip** — id, name, start_date, end_date, total_budget_kr, themes (JSON array), trip_dir, notes (link to overview.md)
- **location** — id, trip_id, name, arrival_date, departure_date, accommodation_place_id
- **day** — id, trip_id, date, location_id, title, energy_level, summary, notes_path
- **place** — id (slug), trip_id (nullable for global), name_en, name_local, category, subcategory, address, lat, lng, google_place_id, tabelog_url, website_url, price_tier, requires_booking, booking_status, booking_lead_time_weeks, tags (JSON), notes_path
- **day_place** — day_id, place_id, time_slot, visit_order, duration_minutes, specific_notes
- **souvenir** — id, trip_id, recipient, item_name, category, estimated_cost_kr, weight_g, sourced_from_place_id, status
- **budget_line** — id, trip_id, category, planned_amount_kr, actual_amount_kr, notes
- **map_registry** — trip_id, map_name (e.g. `Nagoya-11/2026`), my_maps_url, last_generated_at

Rules:
- `place.trip_id` is nullable. Default is trip-scoped. Promote to global only on explicit user request.
- `notes_path` fields are *paths to markdown files relative to repo root*. Markdown stays canonical.
- DB is regenerated by `tp parse <trip-slug>`. Don't write to it directly except via the sync script.
- No versioning in DB. Git versions the markdown; DB is ephemeral.

---

## CLI surface (phase 1)

Use `typer`. All commands accept `--trip <slug>` or are scoped by `cwd` when run inside a trip directory.

```
tp trip new <slug> [--from-template]   # scaffold a new trip directory
tp trip list                            # list all trips with status
tp parse <trip-slug>                    # parse markdown → DB
tp map generate <trip-slug>             # produce my-maps.csv + daily-routes.md + places-index.md
tp map open <trip-slug>                 # open the stored My Maps URL in browser
tp map register-url <trip-slug> <url>   # store the My Maps URL after first manual import
tp doctor                               # check API keys, MCP server, DB schema, places.yaml validity
```

Map name format: `<TripName>-<MM>/<YYYY>` (e.g. `Nagoya-11/2026`). Used as the My Maps map title AND the lookup key in `map_registry`.

Natural-language invocation pattern (what Patrizio will actually type to Claude):
- "Show me the map for Nagoya" → `tp map open nagoya-2026-11` (resolving "Nagoya" by fuzzy match on trip names, prompting if ambiguous)
- "Regenerate the Nagoya map" → `tp map generate nagoya-2026-11`
- "Parse the latest Nagoya changes" → `tp parse nagoya-2026-11`
- "Open the Nagoya CSV" → open `trips/nagoya-2026-11/output/my-maps.csv` in default app

When Patrizio uses fuzzy trip references ("Nagoya"), resolve via `tp trip list` and confirm if multiple match.

---

## Markdown conventions (CRITICAL)

Trip markdown follows a specific structure so the parser is reliable. Two-layer approach: structured YAML for machine, prose for humans.

### Trip-level frontmatter

Every trip's `trip.md` starts with YAML frontmatter:

```yaml
---
trip_id: nagoya-2026-11
name: Nagoya November 2026
start_date: 2026-11-XX     # TBD until locked
end_date: 2026-11-XX
total_budget_kr: 25400
themes: [autumn, food-deep, craft-villages, slow-pace]
home_currency: DKK
---
```

### Canonical place list: `places.yaml`

Every trip has a `places.yaml` in its root. This is the SINGLE SOURCE OF TRUTH for structured place data. The parser reads this first; prose mentions in other markdown files are secondary, used only for cross-referencing and validation.

Schema:

```yaml
- id: atsuta-houraiken-honten
  name_en: Atsuta Houraiken (main shop)
  name_local: あつた蓬莱軒 本店
  category: restaurant
  subcategory: hitsumabushi
  address: 503 Godo-cho, Atsuta-ku, Nagoya
  google_place_id: ChIJ...              # filled by places_lookup if missing
  lat: 35.124                            # filled by places_lookup if missing
  lng: 136.908                           # filled by places_lookup if missing
  tabelog_url: https://tabelog.com/en/aichi/A2301/A230112/23000063/
  price_tier: 3
  requires_booking: false
  booking_status: not_started
  tags: [eel, founding-restaurant, walk-in]
  visit_days: [2]                        # which day numbers
  time_slots: [brunch]
  notes: |
    The 1873 inventor of hitsumabushi. Expect 30-60 min wait Sat/Sun.
    Walk-in only.
```

Rules for `places.yaml`:
- `id` is a slug, lowercase, hyphenated, stable. Once set, do NOT rename.
- `category` enum: restaurant, accommodation, sight, shop, bar, market, transit, viewpoint, garden, museum, shrine, temple, onsen, ropeway
- `lat`, `lng`, `google_place_id` are FILLED BY THE LOOKUP SCRIPT, not by hand. Leave blank for new entries — the script will populate.
- `visit_days` is an array of day numbers (1-indexed within the trip).
- Multi-line `notes` use `|` for prose, kept short. Long-form notes go in linked markdown files via `notes_path`.

### Day markdown structure

`days/day-NN.md` has its own frontmatter:

```yaml
---
day_number: 7
date: 2026-11-XX
title: Korankei + flexible evening
location: Nagoya
energy: medium
---
```

Followed by the day's prose. Place references in prose use the slug syntax: `[[atsuta-houraiken-honten]]` so the parser can cross-reference.

### When generating NEW trip docs

When Claude is asked to generate trip docs from scratch (not migrating existing ones):
1. Create the `places.yaml` FIRST, populated with all known places
2. Generate `trip.md` with frontmatter
3. Generate `days/day-NN.md` files with frontmatter, referencing places by `[[slug]]`
4. Generate themed docs (food.md, restaurants.md, etc.) that reference places by slug

This guarantees the parser works on day one.

### When migrating EXISTING prose docs (like the Nagoya 2026 docs)

Patrizio already has 6+ unstructured markdown files for the Nagoya 2026 trip. To migrate:
1. Run a "migration sub-agent" task: extract every distinct place mentioned across all files
2. Build `places.yaml` by hand-curating the extraction (with Claude's help in this Code session)
3. Add frontmatter to existing files
4. Replace ambiguous prose mentions with `[[slug]]` references where it improves clarity (don't be aggressive — prose is still primary for humans)
5. Move the original Nagoya markdown files into `trips/nagoya-2026-11/` under their existing names

Migration is a one-time event per trip and is expected to require human review.

---

## API and external services

### Google Maps Platform
- Used for: Places API (place_id lookup, geocoding), Directions URL construction
- API key in `.env` as `GOOGLE_MAPS_API_KEY`
- Free tier covers our usage (~50 lookups per trip)
- The script calls the REST API directly. The Anthropic MCP server is optional for interactive use but not used by the script.

### Google My Maps
- No API exists. Manual import workflow.
- After first import of a trip's `my-maps.csv`, Patrizio runs `tp map register-url <slug> <url>` to store the map URL in the DB.
- Subsequent regenerations require manual re-import (delete old map, import new CSV). Document this in `output/README.md` per trip.

### Anthropic Google Maps MCP server (optional, for Claude Code interactive use)
- Install: `npm install -g @anthropic-ai/mcp-server-google-maps`
- Add to `~/.claude/settings.json`
- Lets Claude do ad-hoc place lookups, route computation in conversation
- The CLI script does NOT depend on the MCP server. Keep them decoupled.

---

## How Claude should operate in this repo

**At the start of every session**, read in this order:
1. `CLAUDE.md` (this file)
2. `BACKLOG.md`
3. `README.md` (if present)
4. The trip directory currently being worked on (resolve from user message or ask)
5. Glance at `tests/` to confirm test conventions before writing new code

**When the user makes a request**:
- If the request is in phase 1 scope: proceed.
- If the request is out of phase 1 scope: note that it's out of scope, ask whether to add to `BACKLOG.md` or expand scope explicitly. Don't just silently expand scope.
- For natural-language map requests ("show me the map for Nagoya"): resolve to a CLI command and ask for confirmation before running stateful commands.

**When generating code**:
- Python 3.12+, `uv` for dependency management
- `typer` for CLI, `pydantic` for data validation, raw `sqlite3` for DB
- No SQLAlchemy ORM at this scale
- Tests with `pytest`. Every parser and CSV generator function gets a test.
- Type hints throughout. `mypy --strict` should pass.
- Small functions, prefer pure functions where possible.
- Error messages should tell Patrizio what failed AND what to do about it.

**When generating markdown**:
- Always include frontmatter when creating trip files
- Reference places by `[[slug]]` syntax
- Keep `places.yaml` as the structured source
- Don't duplicate structured data between `places.yaml` and prose markdown — prose adds color, structure carries facts

**When modifying schema or major architecture**:
- STOP. Discuss with Patrizio before changing `schema.py`, the directory structure, or the CLI surface. These are decisions, not implementations.

**When you encounter ambiguity in existing markdown**:
- Don't guess. Surface the ambiguity. Examples: a restaurant name that could match multiple places, a date that's "TBD", a price in different currency than expected.
- The migration script for Nagoya WILL hit cases like this. That's expected.

**When the user asks "what's next" or "what should we work on"**:
- Show current phase 1 status from a TODO tracker in `BACKLOG.md`
- Don't propose phase 2 work until phase 1 is shipped (parser works end-to-end on Nagoya, CSV imports cleanly, map URL is registered, `tp map open` works)

---

## Done-definition for phase 1

Phase 1 is done when ALL of the following are true:

- [ ] Repo scaffolded with the structure above
- [ ] `tp doctor` runs and gives a clean health check
- [ ] Nagoya 2026 trip migrated: `places.yaml` populated, all places have lat/lng/google_place_id, frontmatter added to existing files
- [ ] `tp parse nagoya-2026-11` populates the DB without errors
- [ ] `tp map generate nagoya-2026-11` produces:
  - `my-maps.csv` that imports cleanly into Google My Maps
  - `daily-routes.md` with one Google Maps directions URL per day
  - `places-index.md` with all places, organized by category, with deep links
- [ ] CSV imported into My Maps under the title `Nagoya-11/2026`
- [ ] `tp map register-url nagoya-2026-11 <url>` stores the URL
- [ ] `tp map open nagoya-2026-11` opens the My Maps URL in browser
- [ ] Natural-language flow works: Patrizio says "show me the map for Nagoya" in Claude Code, Claude resolves and opens it
- [ ] Tests pass: parser tests, lookup tests, CSV generation tests
- [ ] `BACKLOG.md` updated with deferred items
- [ ] One short post-mortem in `BACKLOG.md` listing what was harder than expected

When all checked: Phase 1 ships. We then have an explicit conversation about Phase 2 scope before any new feature work.

---

## What this is NOT

To make scope creep obvious:

- ❌ A traveler profile system
- ❌ A questionnaire flow
- ❌ A trip recommendation engine
- ❌ A calendar integration
- ❌ A booking system or Tabelog integration
- ❌ An email drafting system
- ❌ A web dashboard
- ❌ A mobile app
- ❌ A flight price tracker
- ❌ A currency conversion service
- ❌ A weather integration
- ❌ A multi-traveler / shared-trip system
- ❌ An LLM-powered question-answering system on top of trip docs (Obsidian + Claude Code already do this)
- ❌ A "smart" sync that writes back to Google Maps personal saved places (no API exists)
- ❌ A "smart" sync that reads pins added in the Maps app and merges them back (no API exists)

These are all interesting. None of them are phase 1.

---

## Patrizio context Claude should hold

These are durable facts about the human operating this system. They inform recommendations but aren't preferences to enforce blindly.

- Italian, originally Rome, based in Copenhagen
- AI/ML engineer at InterHuman (previously Mimiry, GPU compute startup)
- Physics MSc background; likes geometric and physical intuitions
- Heavy Claude Code user; terminal-first; tmux + worktrees; Obsidian as second brain
- Strategy-first; values sparring intellectual exchange
- Slow, food-deep, sensory-immersive travel style
- Strong opinions on food: hates redundancy in food experiences across a trip (the kaiseki removal was a Patrizio-driven decision because four minshuku dinners covered the register)
- Singular-experience-per-trip filter ("what can ONLY happen this season this year")
- Saves ~700 kr/week toward trips; uses ferie penge for cash flow

When making recommendations or generating prose, this context should shape the voice and the substance.

---

*Version: 0.1 (draft)*
*Last updated: at project bootstrap*
*Next review: when phase 1 ships*
