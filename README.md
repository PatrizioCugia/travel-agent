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
# and register it (written to trip.md's frontmatter as my_maps_url, so it
# survives every re-parse):
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

## Phase 2 — finding lodging and food (Rakuten + Places, over MCP)

Phase 1 turns markdown into maps. Phase 2 is the other direction: research the
places in the first place, from inside Claude Code, and end every answer at a
URL you book yourself. Nothing here books, holds, or writes to any reservation
system — no Japanese OTA exposes a public write path, and we do not pretend
otherwise.

### One-time setup

```bash
# 1. Rakuten Web Service app (free, instant, no review)
#    https://webservice.rakuten.co.jp/app/list → +アプリID発行
#    - Application type: API/backend  (NOT "web" — requests come from a
#      Python process, not a browser page)
#    - Allowed IPs: your current public IP, one per line
#    - API scopes: Rakuten Travel API only
#    Copy applicationId and accessKey into .env:
#      RAKUTEN_APP_ID=...
#      RAKUTEN_ACCESS_KEY=...
#      JPY_PER_DKK=24.8      # display only, hand-maintained

# 2. Verify — checks both keys and prints your public IP for the allowlist
uv run tp doctor
```

**The IP allowlist is the thing that will break.** The app is pinned to your
public IP, which on a residential ISP lease changes without warning. It also
breaks the moment a VPN is on, and while you are travelling — including in
Japan. When Rakuten starts refusing calls, `tp doctor` prints the current IP;
paste it into the app settings and you are working again.

### Searching

```bash
# Lodging near any place Google Places understands
uv run tp lodging search "Kinosaki Onsen" --checkin 2027-03-05 --nights 2 --dinner
uv run tp lodging search "Naramachi Nara" --checkin 2027-03-11 --nights 1 --onsen

uv run tp lodging resolve "城崎温泉 東山荘"    # name → hotelNo (Japanese works better)
uv run tp lodging show 5719                    # check-in times, bath, facilities

# Restaurants — Google Places, with a Tabelog search link per result
uv run tp food search "Todai-ji Nara" --dish kamameshi
```

Prices show as yen with an approximate kroner figure, and cover **the first
night only** — Rakuten's `dailyCharge` does not sum a multi-night stay. Results
carrying a `(first night)` marker are telling you exactly that.

Keep the Japanese property name, address, and local terms as the canonical
identity. Query Rakuten, Jalan where an existing sanctioned key is available,
and an operator's Japanese site before relying on an English-language
aggregator. English results are useful navigation aids, but do not represent
the whole domestic market.

### Booking routes after a Rakuten empty result

Use `check_availability` for the exact dates first. If Rakuten returns no
plan, call `booking_route` with the same hotel number. It looks up reviewed
alternative IDs and official booking or contact paths in
`data/booking_routes.yaml`; it does not claim the inn is full and it never
submits a booking or an enquiry.

Jalan is recorded when a matching Jalan property ID is verified. Its legacy Web
Service can return Jalan-channel stock and a date-specific booking redirect,
but Recruit no longer issues new API keys. Treat it as an optional second API
only if a sanctioned legacy key already exists; otherwise use the returned
Jalan booking page by hand. Its stock is not the inn's total remaining rooms.

### Onsen, sento, and tattoo access

`discover_nearby` first checks a reviewed Japanese destination/operator
directory when its onsen query exactly matches a covered town or bath (for
example, `城崎温泉`). This fills named public-bath gaps in OpenStreetMap without
scraping a directory. Other locations fall back to OSM candidates. A directory
entry says that an official day-use schedule is published; it is not a
real-time open signal.

Neither discovery source can establish tattoo, day-use, or private-bath policy
on its own. Use `bathing_access` with the exact Japanese bath name to retrieve
only reviewed, source-linked evidence from `data/bathing_access.yaml`. The
current source contract and extension rules are in
[`BATHING_DISCOVERY_SCOPE.md`](BATHING_DISCOVERY_SCOPE.md).

The hierarchy is deliberate: a current operator statement is authoritative;
an official destination or municipality can confirm a shared public-bath rule;
Tattoo Navi and Tattoo Japan are useful discovery leads. A policy missing from
the registry is `unknown`, not a rejection. Keep public baths and the baths
inside a ryokan separate: a town-wide public-bath rule does not automatically
cover accommodation baths.

### Shortlist → trip

Search results are noise until you keep one. Candidates land in
`trips/<slug>/shortlist.yaml`, which uses the same entry schema as
`places.yaml` plus a `_found` provenance block, so promotion is a move rather
than a retype:

```bash
uv run tp shortlist list japan-2027-02
uv run tp shortlist promote japan-2027-02 higasiyama-sou   # → places.yaml
uv run tp parse japan-2027-02                              # picks it up, maps it
uv run tp shortlist remove japan-2027-02 <id>
```

### Watching for calendars that have not opened

Small ryokan open their booking calendars three to six months out, on no
published schedule and with no notification. Rakuten returns the **same** empty
answer for a sold-out stay, an unpublished calendar, and a property that has
not supplied bookable plan inventory to Rakuten. An empty result is never
reported as proof a place is full.

```bash
# Exact dates
uv run tp watch add 5719 --label "Higashiyamaso 東山荘" \
    --checkin 2027-03-05 --checkout 2027-03-07 --trip japan-2027-02

# Or a window, while dates are still moving — one watch per candidate check-in
uv run tp watch add 7850 --label "Nara Hakushikaso" \
    --window 2027-03-01..2027-03-14 --nights 1 --trip japan-2027-02

uv run tp watch list --trip japan-2027-02
uv run tp watch run          # poll once; this is what the schedule runs
uv run tp watch log          # what the scheduled runs found since you last looked
uv run tp watch remove 12    # deactivate, keeping its history
```

Watches batch by date: a dozen inns on the same night cost one API call, not
twelve. Reported transitions are `opened`, `closed`, `new_plan` and
`price_drop`; `opened` is the one that matters and it deliberately subsumes the
others, so an inn opening its calendar is one line, not fifteen.

### Running it nightly

```bash
cp ops/com.patrizio.tp-watch.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.patrizio.tp-watch.plist
```

launchd rather than cron, for one reason: this laptop sleeps, and cron silently
skips a job whose time passed while the machine was asleep. launchd runs the
missed job on wake. For a watcher whose whole value is catching a calendar the
day it opens, a silently skipped night is the failure that matters. It does not
catch up a night the Mac spent shut down. One failed date batch does not stop the
others; the run is recorded as incomplete and exits non-zero. Output goes to
`data/watch.log`; findings accumulate in `tp watch log`.

### Using it from Claude Code

`.mcp.json` registers the MCP server for this project, which is the normal
interface: `trip_overview` and `validate_trip` read the canonical Markdown;
lodging/food/OSM tools discover candidates; shortlist tools retain and promote
decisions; `sync_trip` and `generate_trip_map` rebuild derived state; watches
hold availability history. Claude can chain these capabilities in one turn.
They return compact text, never raw JSON; Rakuten payloads are enormous and
worthless in context.

The server reads `.env` itself, so no secrets live in `.mcp.json`.

`.claude/skills/japan-lodging/SKILL.md` is the taste layer on top: half-board
minshuku in the countryside, low-friction hotels in cities, one singular
experience per trip, no food redundancy. The tools stay neutral so you can
always ask for the boring option.

### Two databases, and why

- `data/travel_planner.db` — the phase-1 index. Regenerable; `tp parse` deletes
  and rebuilds a trip in it.
- `data/observations.db` — watch targets, availability history, change log.
  **Never** touched by `tp parse`.

The split is structural rather than a rule to remember: `tp parse` deletes a
trip and cascades to its children, so any snapshot table with a real `trip_id`
foreign key would be destroyed on every parse — taking the diff baseline, and
with it the entire point of the watcher. Plan state is disposable and
git-versioned through markdown; world state is observed once and cannot be
recovered.


## Files of interest

- `CLAUDE.md` — project conventions (read at the start of every Claude Code session).
- `PLAN.md` — phase-1 design plan, six-step shape.
- `PLAN-PHASE2.md` — phase-2 design plan: lodging/food research layer.
- `PHASE2_KICKOFF.md` — the brief phase 2 was built from.
- `M1-findings.md` — research output that drove M3 + M5 design.
- `BACKLOG.md` — deferred work + phase-1 post-mortem.
- `nagoya_2026_v0_source_of_truth.md` — the input doc M6 migrated from.

---

*"What can only happen this season, this year?" — the filter that picks the trip.*
