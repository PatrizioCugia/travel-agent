# travel-planner

Personal travel planner. You write trip notes as markdown; it produces a Google My Maps CSV (plus KML, daily-routes, place index, and tap-to-save deeplinks) so the whole trip lives on one map you can open from your phone. CLI + Claude Code as interface.

**Status**: phase 1 shipped. The Nagoya 2026 trip is fully migrated and importable from `trips/nagoya-2026-11/output/`. See `PLAN.md` for design decisions, `M1-findings.md` for the Places API + My Maps research, and `BACKLOG.md` for what's deferred.

---

## What it does

Three things, in order:

1. **You author trip notes** as markdown — a `places.yaml` listing every place (slug, name, category, address, notes), a `trip.md` with frontmatter, and one `days/day-NN.md` per day referencing places via `[[slug]]`.
2. **`tp parse <slug>`** validates the markdown, hits Google Places API to fill in missing `lat/lng/google_place_id`, writes results back to `places.yaml` (formatting preserved), and syncs everything to a local SQLite index.
3. **`tp map generate <slug>`** turns the DB into six artifacts in `trips/<slug>/output/`: `my-maps.csv` (import into Google My Maps), `my-maps.kml` (alternative with per-category icons), `daily-routes.md` (one Google Maps directions URL per day), `places-index.md`, `saveable-places.md` (per-place tap-to-save deeplinks), and a workflow `README.md`.

The CSV gets imported manually into Google My Maps (one-click), the resulting URL is stored with `tp map register-url`, and `tp map open` jumps to it from the terminal.

Markdown is canonical. SQLite is a regenerable index. Re-running `tp parse` is free — successful lookups cache to disk.

---

## Quick start (first time setup)

You need: macOS or Linux, Python 3.12+ (auto-installed by `uv`), a Google Cloud project with the **Places API (New)** enabled, and ~10 minutes.

```bash
# 1. Clone and install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"  # add to ~/.zshrc to persist

# 2. From the repo root, sync dependencies (creates .venv/, installs everything)
uv sync --extra dev

# 3. Get a Google Maps API key
# - https://console.cloud.google.com → new project "travel-planner"
# - Link a billing account (free tier is generous; set a $1 alert)
# - APIs & Services → Library → enable "Places API (New)" (NOT the legacy one)
# - APIs & Services → Credentials → Create credentials → API key
# - Edit the key → restrict to "Places API (New)"
# - Copy the key

# 4. Drop the key into .env
cp .env.example .env
$EDITOR .env  # paste the key after GOOGLE_MAPS_API_KEY=

# 5. Verify
uv run tp doctor
# Should print: ok Python ..., ok GOOGLE_MAPS_API_KEY set, ok DB writeable, ok trips/ exists
```

That's it for setup. The `tp` binary is exposed by `uv sync` and lives at `.venv/bin/tp`; the `uv run tp ...` form picks it up without activating the venv.

---

## Daily workflow on an existing trip

Using the Nagoya 2026 trip that ships with the repo:

```bash
# Parse (validates + hits Places API + caches + syncs DB)
uv run tp parse nagoya
# Fuzzy: "nagoya" resolves to "nagoya-2026-11"

# Re-parse after editing markdown — successful lookups are cached, so re-runs are cheap
uv run tp parse nagoya

# Generate the six output artifacts under trips/nagoya-2026-11/output/
uv run tp map generate nagoya

# Now do the manual My Maps import (~30 seconds):
#   1. Open https://www.google.com/mymaps in a browser.
#   2. + Create a new map.
#   3. Click Import on the unnamed layer.
#   4. Drop trips/nagoya-2026-11/output/my-maps.csv.
#   5. Wizard step: pick `latitude` + `longitude` as location columns.
#      (This skips Google's geocoder and is deterministic for Japanese addresses.)
#   6. Wizard step: pick `name` as the title column.
#   7. After import: layer menu → Style by data column → `category` (one click).
#      Pins are now color-coded; the style rule persists across re-imports.
#   8. Rename the map to "Nagoya-2026-11" (top-left field).

# Copy the map URL from the browser's address bar (looks like
# https://www.google.com/maps/d/edit?mid=...&...)
# and register it:
uv run tp map register-url nagoya 'https://www.google.com/maps/d/edit?mid=YOUR_MAP_ID'

# Open the map any time
uv run tp map open nagoya
```

**Re-import workflow**: after changing markdown and re-running `tp map generate`, open the same My Maps map → layer menu → **Delete layer** → **Import** the new CSV → choose **Replace layer**. The "Style by category" rule is preserved.

---

## Authoring a new trip

```bash
# Create the directory
mkdir -p trips/<slug>/days

# Author trip.md (frontmatter + overview prose)
cat > trips/<slug>/trip.md <<'EOF'
---
trip_id: <slug>
name: <Display name>
total_budget_kr: 25000
themes: [autumn, food-deep]
---

# Trip title

Brief overview.
EOF

# Author places.yaml — one entry per place
# See trips/nagoya-2026-11/places.yaml for the canonical reference
cat > trips/<slug>/places.yaml <<'EOF'
- id: example-cafe
  name_en: Example Cafe
  name_local: 例カフェ
  category: cafe
  address: Sakae, Naka-ku, Nagoya
  tags: [breakfast]
  notes: One short paragraph describing what makes this place worth visiting.
EOF

# Author one days/day-NN.md per day with [[slug]] references in prose
cat > trips/<slug>/days/day-01.md <<'EOF'
---
day_number: 1
location: Nagoya
title: Arrival
---

Land mid-afternoon. Drop in at [[example-cafe]] for coffee.
EOF

# Validate + lookup + sync
uv run tp parse <slug>

# Generate the import artifacts
uv run tp map generate <slug>
```

The `category` field must be one of: `restaurant, accommodation, sight, shop, bar, cafe, market, transit, shrine, temple, garden, museum, onsen, ropeway, viewpoint`. The `id` (slug) must match `^[a-z0-9]+(?:-[a-z0-9]+)*$` (lowercase kebab-case, optional leading digit). `lat`, `lng`, and `google_place_id` are filled in by `tp parse` — leave them out of new entries.

For day prose, reference places with `[[slug]]` syntax (Obsidian-style `[[slug|alias]]` also works — alias is for display, the slug is what links into the place). Dangling references error out before the DB write.

---

## CLI reference

```
tp doctor                          Health check (Python ver, API key, DB, trips/)
tp trips                           List all trips under trips/

tp parse <slug> [--no-lookup] [--force]
                                   Parse a trip's markdown into the DB.
                                   --no-lookup: skip Places API
                                   --force:     re-lookup every place

tp map generate <slug>             Produce my-maps.csv, KML, daily-routes,
                                   places-index, saveable-places, README.

tp map register-url <slug> <url>   Store the My Maps URL after import.

tp map open <slug>                 Open the registered map URL in browser.

tp spike                           Sanity-check Places API with one hardcoded
                                   lookup. Writes spike.csv.
```

Slugs accept fuzzy matches (exact → substring → `rapidfuzz` partial). `nagoya` resolves to `nagoya-2026-11`. Ambiguous matches list candidates and exit non-zero.

---

## Trip directory structure

```
trips/<slug>/
├── trip.md                   Frontmatter (name, dates, themes, budget) + overview
├── places.yaml               Canonical place list (all ~50–70 places)
├── days/
│   ├── day-01.md             Frontmatter + prose with [[slug]] refs
│   ├── day-02.md
│   └── ...
└── output/                   Generated by `tp map generate` — gitignored
    ├── my-maps.csv
    ├── my-maps.kml
    ├── daily-routes.md
    ├── places-index.md
    ├── saveable-places.md
    ├── lookup-misses.md      Written by `tp parse` when a lookup fails
    └── README.md             Import-workflow docs
```

---

## Working with Claude Code

This project is built to be operated via Claude Code in a terminal pointed at the repo. Natural-language commands map to `tp` invocations:

- "Show me the map for Nagoya" → `tp map open nagoya`
- "Parse the latest Nagoya changes" → `tp parse nagoya`
- "Regenerate the map artifacts" → `tp map generate nagoya`
- "What restaurants are planned in Nagoya?" → Claude reads `places.yaml` and answers
- "Make an itinerary for Day 4" → Claude reads `days/day-04.md` and `places.yaml` and proposes

The CLI is plumbing; the seamless agent interface is the real product.

---

## How to test it locally

After the Quick-start setup:

```bash
# Run the test suite (100 tests, fast)
uv run pytest -v

# Lint + format check
uv run ruff check .
uv run ruff format --check .

# Strict type check
uv run mypy

# Spike: one live Places API call → 1-row CSV at ./spike.csv
uv run tp spike
# Manually drop spike.csv into a throwaway My Maps map to confirm the
# import wizard, the kanji-rendering, and the lat/lng-skips-geocoder flow.

# Full Nagoya flow (uses the trip that ships with the repo)
uv run tp parse nagoya
uv run tp map generate nagoya

# Inspect the outputs
open trips/nagoya-2026-11/output/  # macOS: opens in Finder
# Or read individual files:
cat trips/nagoya-2026-11/output/daily-routes.md
cat trips/nagoya-2026-11/output/places-index.md
```

If a place needs manual correction (see `lookup-misses.md`), edit `trips/nagoya-2026-11/places.yaml` directly — either tighten the name/address and re-run `tp parse`, or paste a manually-looked-up `google_place_id`, `lat`, and `lng` into the entry.

---

## Architecture (one paragraph)

Python 3.12+, `uv` for deps, `typer` for CLI, `pydantic` v2 for validation, `ruamel.yaml` for round-trip writes, `rapidfuzz` for slug resolution, raw `sqlite3` for the DB, `requests` for Places API (New). Markdown is the canonical store; the SQLite DB is regenerated by `tp parse` (3-table + 1-join schema: `trip`, `place`, `day`, `day_place`). Places API lookup is per-trip, region-aware (address keyword → bias center), with a 50 km distance gate to reject high-confidence-but-wrong-region matches. All output generators are pure functions `(view data) → string`; the orchestrator does file I/O. Tests: 100, mypy --strict, ruff. Phase 1 done; future phases (calendar, bookings, recommendations) on the backlog.

## What's not here (phase 1 scope)

- No booking, email, or calendar integration.
- No write API to Google's personal saved places (none exists from Google).
- No web UI.
- No agentic actions — `tp` is pure markdown-in, files-out. Claude orchestrates by reading markdown and calling these commands.
- No multi-traveler or shared-trip support.

These are interesting; none of them are phase 1. See `BACKLOG.md`.

---

## Files of interest

- `CLAUDE.md` — project conventions (read at the start of every Claude Code session).
- `PLAN.md` — phase-1 design plan, six-step shape.
- `M1-findings.md` — research output that drove M3 + M5 design.
- `BACKLOG.md` — deferred work + phase-1 post-mortem.
- `nagoya_2026_v0_source_of_truth.md` — the input doc M6 migrated from.

---

*"What can only happen this season, this year?" — the filter that picks the trip.*
