# PLAN-PHASE2.md — lodging & food research layer

*Output of the phase 2 planning session. Phase 1's `PLAN.md` is left intact as a record.*
*Status: awaiting approval. No implementation code written yet.*

## 1. What changed from the kickoff

The kickoff (`PHASE2_KICKOFF.md`) frames the watcher as the product and search as
plumbing. In conversation Patrizio inverted that:

> "I would like to be able to know stuff from hotels, ryokans etc. using claude code
> as an interface … helping me find hotels and restaurants. Then using information
> from here to do the bookings myself."

So: **the product is research, the watcher is one feature inside it.** Everything
below reflects that. The kickoff's hard constraints are unchanged and unargued —
Jalan is dead, Tabelog has no API, no write path exists, nothing books.

Decisions taken in that conversation, now settled:

| Question | Answer |
|---|---|
| Interface | MCP server, project-scoped in this repo, used from Claude Code |
| Restaurants | Google Places (already wired) + constructed Tabelog links. No Hot Pepper. |
| Search results | Written to a per-trip shortlist file, promotable into `places.yaml` |
| Trip | Scaffold `japan-2027-02` now |
| Watcher | Stays in scope, terminal-only alerts, no push infrastructure |
| Taste | Neutral tools + a separate skill that encodes preferences |
| Lodging result fields | price + meal plan, review score, bath/onsen type, location + station |
| Food result fields | near-a-place by dish, reservation-likely flag, Tabelog link |

## 2. Trip facts (as given)

- **Two travellers** (Patrizio + sister). `adultNum=2, roomNum=1`.
- **Late February – early March 2027**, 18–19 nights.
- Tokyo 4 / Kyoto 2 / Osaka 3 / Hiroshima 2 / Fukuoka 2 / Nara 1 (all nights),
  plus 2 nights countryside ryokan, plus 2–3 more countryside nights TBD.
- **Nara night must fall inside 1–14 March 2027** — Omizutori at Todai-ji, approved
  as this trip's singular experience. This is a hard constraint on the date frame,
  and it makes Nara the highest-urgency watch target: little lodging, busiest
  fortnight of its year.
- Budget: not yet set. Every price filter is therefore optional, never required.

**Consequence for the design:** exact dates are not locked, so the watcher must
handle **date windows**, not single date pairs. `--window 2027-02-25..2027-03-15
--nights 2` expands to one target per candidate check-in. Rakuten batches 15 hotels
per call per date pair, so a dozen inns across a 15-day window is 15 calls, not 180 —
comfortably inside the 1 QPS we declared.

## 3. The durability problem — answer

**Chosen: (a), a second database file.** `data/travel_planner.db` stays the
regenerable planning index. `data/observations.db` holds watch targets and
availability snapshots, and `tp parse` never opens it.

The argument is not tidiness, it's that (b) is already broken in the existing code.
`sync_trip()` does `DELETE FROM trip WHERE id = ?` against a schema whose children
declare `ON DELETE CASCADE`. Any observation table carrying a real `trip_id`
foreign key is destroyed on every parse; any that omits the key is lying about the
relationship. "Mark certain tables as durable" means maintaining, forever, a list of
tables the delete must dodge — a rule enforced by memory, in the one place where
forgetting silently destroys the diff baseline that makes the watcher work.

Two files make the boundary structural. Plan state is disposable and git-versioned
through markdown; world state is observational and irreplaceable. They get different
lifecycles because they *are* different.

Cost: cross-database joins need `ATTACH DATABASE`. That is one line in the two
queries that need it (`watch list`, `booking status`), and SQLite handles it without
ceremony. Accepted.

Rejected: (c) JSONL — puts the diff baseline in a format with no query surface, and
"what has this inn done over six months" is a question we will want. (d) — nothing
better presented itself.

## 4. Schema changes

### Planning DB (`travel_planner.db`) — one new column

```sql
ALTER TABLE place ADD COLUMN rakuten_hotel_no INTEGER;
```

Sourced from `places.yaml`, not written by hand into the DB — same contract as
`google_place_id`. `maps/yaml_writer.py` already does exactly this round-trip for
Places enrichment; `resolve_inn` reuses that path. Markdown stays canonical.

**`booking_status` — proposal, needs your yes/no.** The kickoff says it should stop
being hand-maintained and become derived. Phase 1 deliberately deleted the column and
put status in `tags` (`booking-needed`). I propose *not* reintroducing the column:
keep the tag as the human's declaration of intent, and expose observed state as a
derived view joining `place` to the latest snapshot, so `tp watch list` and the MCP
tools answer "you said you need to book this, and it is currently bookable at ¥X"
without a column that can disagree with the markdown. Per CLAUDE.md, schema changes
are decisions, not implementations — so this one is yours.

### Observations DB (`observations.db`) — new file

`watch_target` and `availability_snapshot` essentially as in `watch.py`, with fixes:

- `trip_id` / `place_id` are plain columns, not foreign keys (cross-database FKs
  don't exist, and the honesty is the point).
- `UNIQUE (hotel_no, checkin, checkout, adults, rooms)` retained, but `add_target`
  reactivates a matching `active = 0` row instead of silently returning it inert.
- Latest-snapshot lookups order by `(polled_at DESC, id DESC)` — two polls inside one
  second currently tie non-deterministically.
- New `watch_run` table: one row per scheduled execution (started, finished, targets
  polled, changes found, error). Without it, "did the nightly run actually happen"
  is unanswerable, which is the classic way a watcher dies quietly.

## 5. Module layout

```
src/travel_planner/
├── lodging/
│   ├── rakuten.py        # the reference client, moved, substance unchanged
│   ├── search.py         # geocode-then-vacancy, result shaping
│   ├── watch.py          # targets + snapshot + diff, fixed per §7
│   └── observations.py   # observations.db connection + DDL + ATTACH helper
├── food/
│   └── search.py         # Places searchText, Tabelog link, booking-likely heuristic
├── shortlist.py          # read/write trips/<slug>/shortlist.yaml, promote to places.yaml
├── format.py             # ¥/kr, name lines, the one place output style lives
└── mcp_server.py         # FastMCP, thin wrappers over the above
```

Nothing in `parser/`, `db/`, `maps/` or `output/` changes except the one new column.

**Dependencies:** add `httpx` (keep `requests` for the existing Places code — porting
a working, tested client to satisfy consistency is churn, not improvement) and `mcp`.

## 6. Shortlist format

`trips/<slug>/shortlist.yaml`, git-versioned, human-editable. Entry schema is
*identical to a `places.yaml` entry* plus one provenance block, so promotion is a move
rather than a retype:

```yaml
- id: kinosaki-nishimuraya-honkan
  name_en: Nishimuraya Honkan
  name_local: 西村屋本館
  category: accommodation
  address: 469 Yushima, Kinosaki-cho, Toyooka, Hyogo
  rakuten_hotel_no: 12345
  tags: [ryokan, onsen, kaiseki, crab-season]
  notes: |
    Seven public baths walkable in yukata. Matsuba crab season ends ~20 March.
  _found:
    source: rakuten
    query: "城崎温泉 2027-03-04 2 adults"
    at: 2026-08-22
    review: "4.6 (312)"
    seen_price_yen: 38000
```

`tp shortlist promote <id>` moves the mapping into `places.yaml`, strips `_found`,
and leaves the shortlist entry deleted. Candidates never pollute the map pipeline
until promoted.

## 7. What I'd change in the reference implementation

> **Status (2026-09-16): all nine defects below are fixed in the shipped code**
> — repo-rooted DB paths, reactivating `add_target`, `remove_target`, strict
> mypy, loud missing `hotelNo`, first-night caveats in alerts, no B905, tests in
> `tests/test_watch.py` and `tests/test_rakuten_parse.py`, snapshots on change
> only. The list is kept as design history, not as open work.

`rakuten.py` is good and its nine gotchas are real — I verified both endpoint version
strings against the live docs (`VacantHotelSearch/20170426`,
`KeywordHotelSearch/20260731`) and the `accessKey` requirement and `datumType=2`
default. Live smoke test passed against the real API. Substance stays. Defects:

1. **`mcp_server.py` defaults `TP_DB` to `"tp.db"` relative to cwd.** Launched from
   anywhere else it silently creates an empty database and reports "No active
   watches". Must use the existing `_repo_root()` resolution.
2. **`add_target` cannot reactivate.** `INSERT OR IGNORE` on the unique key returns a
   deactivated row without reactivating it — a watch that looks added and never runs.
3. **No remove/deactivate function** exists, though `tp watch remove` is in scope.
4. **`mypy --strict` will reject `watch.py`**: `poll()` annotates `list[sqlite3.Row]`
   but indexes tuples, and `_diff` / `_summarise` / `_best` are unannotated with bare
   `dict`. The repo is strict-clean today and stays that way.
5. **`Hotel.hotel_no` silently defaults to `0`** on a missing field. Fail loudly.
6. **`price_drop` compares first-night prices only.** `dailyCharge` covers night one
   (gotcha 6), so on a multi-night watch "¥38,000 → ¥34,000" is not the trip price.
   Documented in a docstring, invisible in the alert. The alert must say so.
7. **`dict(zip(...))` in `search_lodging`** trips ruff B905 under the repo's config.
8. **No tests.** The kickoff describes a four-day simulated diff sequence; that file
   isn't among the three modules. The diff state machine is the part most worth
   testing and it will be tested.
9. **Snapshots are written unconditionally on every poll**, so the table grows one row
   per target per run forever. Small, but I'd write only on change plus a periodic
   heartbeat row, which also makes the history readable.

Additionally, from live setup: **the Rakuten app is IP-allowlisted** to a dynamic
residential ISP address. When it rotates, calls fail. `tp doctor` will report the
current public IP so a mystery rejection is a one-command diagnosis, and the client
will name the allowlist in its error rather than echoing Rakuten's bare body.

## 8. CLI surface

Consistent with the existing typer app:

```
tp lodging search <where> --checkin --checkout [--nights] [--onsen] [--dinner]
                          [--max-yen] [--radius-km]     # where = place name or slug
tp lodging show <hotel_no>                              # detail + plans + reserve URL
tp food search <near> [--dish] [--open-on] [--min-rating]
tp shortlist list <trip> [--category]
tp shortlist promote <trip> <id>
tp watch add <hotel_no> --label --checkin --checkout | --window A..B --nights N
tp watch list [--trip]
tp watch run [--quiet]
tp watch remove <id>
tp watch log [--since]
tp doctor                                               # + Rakuten keys, public IP
```

## 9. MCP surface

`.mcp.json` at repo root, project scope. All tools return compact text — never
raw JSON. Rakuten payloads are enormous and worthless in context.

> **Status (2026-09-16):** the shipped surface outgrew the ten tools planned here.
> `CLAUDE.md` is the maintained reference; as built there are 24:

- Trip state: `trip_overview` · `validate_trip` · `sync_trip` · `generate_trip_map` ·
  `check_day_feasibility`
- Discovery: `discover_nearby` · `bathing_access` · `bathing_access_audit`
- Lodging: `find_lodging` · `resolve_inn` · `check_availability` · `booking_route` ·
  `booking_route_audit` · `lodging_detail`
- Food: `find_food`
- Shortlist (`shortlist_add` split by source): `shortlist_show` ·
  `shortlist_add_lodging` · `shortlist_add_restaurant` · `shortlist_add_activity` ·
  `shortlist_promote`
- Watching: `watch_add` · `watch_list` · `watch_run` · `watch_news`

Prices: Rakuten's `dailyCharge.total` is the whole party's first-night price and
`maxCharge` filters on it; `chargeFlag` only gives the unit of `rakutenCharge`
(verified live 2026-09-16, see `lodging/rakuten.py`).

Lodging line format, per the fields chosen:

```
12345  ¥38,000 (~1,530 kr) 夕朝  Nishimuraya Honkan 西村屋本館
       4.6 (312) · onsen, private bath · Kinosaki-onsen stn 8 min walk
       https://travel.rakuten.co.jp/...
```

`find_lodging` resolves "near Kinosaki Onsen" by geocoding through the existing
Places client, then querying Rakuten by lat/lng — remembering the 3.0 km radius cap —
and falls back to the area-code tree for anything region-wide.

## 10. Scheduling

**launchd, not cron.** A `~/Library/LaunchAgents/` user agent with
`StartCalendarInterval`. The tradeoff that decides it: your Mac sleeps, and cron
simply skips a run that falls during sleep, silently. launchd fires the missed job on
wake. For a watcher whose entire value is catching a calendar the day it opens, a
silently skipped night is the failure mode that matters.

Runs write to `data/watch.log`; changes are kept in `observations.db`'s `change_log`
(the planned `trips/<slug>/watch-log.md` export was not built). `tp watch log`
surfaces what has appeared since you last looked. No push, no email, per your choice —
but `watch_run` rows mean we can always answer whether the thing actually ran.

Note: this stops working while you travel (different IP) and while a VPN is on.
Not solved here; documented. launchd catches up a run missed during sleep, but not
one missed while the Mac is shut down. One failed date batch no longer aborts the
run: the other batches are polled, and the failure is recorded on the run.

## 11. Milestones

- **M1** — deps, package move (`rakuten.py`/`watch.py` → `lodging/`), `tp doctor`
  extension, strict-clean typing, tests for the existing client. No new behaviour.
- **M2** — `lodging/search.py` + MCP server + `.mcp.json`. First real query: Nara,
  1–14 March 2027.
- **M3** — trip scaffold `trips/japan-2027-02/` + `shortlist.yaml` + promote flow.
- **M4** — `food/search.py`, Tabelog links, reservation-likely flag.
- **M5** — watcher: `observations.db`, date windows, diff fixes, launchd agent.
- **M6** — the taste skill, README, phase 2 post-mortem in `BACKLOG.md`.

## 12. Risks and open questions

1. **`booking_status`** — derived view (my proposal) or a real column? Your call.
2. **Dynamic IP** — the allowlist will break without warning. Mitigated by `tp doctor`,
   not solved.
3. **Rakuten's 404 ambiguity** — sold out and calendar-not-open are indistinguishable.
   Surfaced as uncertainty in output, never guessed at.
4. **Dates unlocked** — handled via date windows, but every extra candidate date
   multiplies watch targets. If the frame stays wide for months, revisit.
5. **Nara** — highest urgency. Worth watching before the rest of the build lands.
6. **Trip slug** — `japan-2027-02`, chosen for consistency with `nagoya-2026-11`.

## 13. Out of scope, explicitly

Map visualizer upgrade (GSI tiles, availability-coloured pins). Hot Pepper Gourmet.
Transit routing beyond phase 1. Traveller profile / recommendation engine. Any write
path to any booking system. Push notification infrastructure.
