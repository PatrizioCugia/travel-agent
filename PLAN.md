# PLAN.md — travel-planner phase 1 (v0.2)

*Output of session 1. Session 2 begins implementation against this. Supersedes earlier draft.*

## 1. Understanding

**What it is.** A personal trip planner where markdown is canonical, SQLite is a regenerable index, and Claude is the seamless interface. The CLI (`tp`) is plumbing.

**Phase 1 scope.** Parse Nagoya 2026 markdown into a queryable DB, generate a Google My Maps CSV + daily route URLs + a places index, and provide CLI to (re)generate and open the map. Claude reads markdown/DB to answer planning questions and propose itineraries on demand.

**Out of scope.** Bookings/email/calendar; multi-user; recommendation engines; web UI; writing to Google personal saved places (no API exists); prose-file parsing (v0 doc is the migration input, the 6 source files are obsolete).

**Strongest opinions.**
1. Markdown canonical; DB regenerable.
2. Claude is the interface — schema shaped for agent queries, not CLI UX.
3. No agentic side effects. Pipeline is deterministic.
4. Patrizio-specific. Resist generalization.
5. Simple beats complete. Fewer tables, fewer columns.

**Done definition.** `tp doctor` clean; Nagoya `places.yaml` fully populated; `tp parse` succeeds; `tp map generate` produces three artifacts; CSV imports cleanly into My Maps under `Nagoya-2026-11`; `tp map register-url` + `tp map open` work; "show me the map for Nagoya" in Claude resolves; tests pass; BACKLOG.md + post-mortem written.

## 2. Schema (3 tables + 1 join)

Defined in `src/travel_planner/schema.py`. The DDL is in the same file. Conscious omissions vs the original CLAUDE.md spec:

- No `souvenir` table — souvenirs are places with `tag: souvenir-source`.
- No `budget_line` table — breakdown stays in `trip.md` prose.
- No `map_registry` table — URL lives on the `trip` row.
- No `role` column — backups/alternates are places not attached to `day_place`, with notes.
- No `region` category — region names live in `day.location` (free-form string).
- No `dates_locked` flag — derived from `start_date IS NULL`.
- `notes` always inline + short; long-form lives in `notes_path` markdown.

## 3. Data flow

1. **Edit.** Patrizio (or Claude) edits `places.yaml`, `trip.md`, or `days/day-NN.md`.
2. **Parse.** `tp parse nagoya-2026-11` reads markdown → looks up missing lat/lng via Google Places API → writes back to `places.yaml` (ruamel.yaml round-trip preserves comments/formatting) → rebuilds the trip's DB rows.
3. **Generate.** `tp map generate nagoya-2026-11` writes `output/my-maps.csv`, `output/daily-routes.md`, `output/places-index.md` and updates `trip.my_maps_generated_at`.
4. **Import.** Manual upload of CSV to Google My Maps (~30s).
5. **Register.** `tp map register-url nagoya-2026-11 <url>` stores it on `trip.my_maps_url`.
6. **Open.** `tp map open nagoya-2026-11` opens the URL.

Error paths: lookup misses warn but don't abort other places; dangling `[[slug]]` errors out; TBD dates emit CSV but skip daily-routes; API rate limits cached on (name+address) hash.

## 4. Build order

| # | Name | Size | Sub-agent team? | Deps |
|---|---|---|---|---|
| **M1** | Scaffold + spine spike | S | **Yes** — 2 parallel Opus agents researching (a) Google My Maps CSV format, (b) Places API behavior on Japanese names. Main session bootstraps repo and `tp doctor`. | — |
| M2 | Trip + places parser | M | No | M1 |
| M3 | Places lookup + yaml round-trip | M | No | M2 |
| M4 | Day parser | M | No | M2 (parallel M3) |
| M5 | Output generators (CSV + daily-routes + places-index) | M | No | M3 + M4 |
| **M6** | Nagoya v0 migration | M | **Yes** — 3 parallel Opus agents drafting day files per location (Nagoya / Tsumago / Okuhida). Main session reviews `places.yaml` + `trip.md`. | M5 |
| M7 | Map register + open + fuzzy resolution + post-mortem | S | No | M6 |

## 5. Riskiest unknowns

1. **Google My Maps CSV columns.** Docs are thin. → M1 agent A researches; M1 spike validates empirically.
2. **Places API on Japanese names.** Multiple matches per query, kanji-only entries, chain branches. → M1 agent B researches; M3 first PR probes 5 representative Nagoya entries.
3. **YAML round-trip preservation** with ruamel.yaml. → M3 first test: load + mutate + dump, diff should be field-additions only.

## 6. Decisions made (not asking)

- Slug pattern kebab-case: `nagoya-2026-11`. Map name `Nagoya-2026-11` (no slash).
- Repo stays at current path. CLAUDE.md's `~/projects/travel-planner/` is aspirational.
- `trips/` lives in the repo. Patrizio points Obsidian at it directly (no symlinks).
- Themed files (food.md, late-night-food.md, phrases.md, restaurants.md) are human-only; parser ignores.
- Live-API tests gated by `PYTEST_LIVE=1`.
- `notes` always inline + short; long-form lives in `notes_path` markdown.
- Toolchain: `uv` + `pyproject.toml` (hatchling backend). Python ≥3.12.
- Git: single branch `main`, commit per milestone.

## 7. Google Maps integration ceiling

No API exists to write to Google personal saved places. What's possible (ranked by tightness):

1. **My Maps CSV import** — current path.
2. **KML/KMZ output alongside CSV** — richer pin styling, day-grouped folders. Folded into M5 if research agent confirms it's worth it.
3. **Per-place "Save to Google Maps" deeplinks** — `https://www.google.com/maps/place/?q=place_id:<ID>`. Tap → mobile Maps → star to saved places. Folded into M5 as `output/saveable-places.md` for a curated shortlist.
4. **Daily-route deeplinks** — already in plan as `daily-routes.md`.
5. **Anthropic Maps MCP server** — optional, read-only, in-Claude lookups.

(Memo at `~/.claude/projects/.../memory/project-google-maps-integration-options.md` for future me.)
