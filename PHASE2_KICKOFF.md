# Claude Code kickoff — `tp` Phase 2: availability & booking layer

> Paste this as the opening message of a fresh Claude Code session in the
> `travel-planner` repo. It is deliberately written to stop the agent
> re-deriving a day of API research that has already been done, and to
> stop it wandering into three specific dead ends.

---

## Read first

Read `CLAUDE.md` and skim `tp/` before responding to anything below. Phase 1
(markdown → SQLite → Google My Maps CSV + daily route URLs) is shipped and
working. Do not restructure it.

**Produce `PLAN.md` before writing any implementation code.** Same rule as
Phase 1. I want to review the plan, argue with it, and approve it before a
single module is touched. If the plan is obvious and short, that's fine —
short is not a failure state.

---

## What we're building

A **read + watch + deep-link** layer over Rakuten Travel, exposed to Claude
Code over MCP.

The problem: small ryokan and minshuku open their booking calendars for a
given date somewhere between three and six months out, on no published
schedule and with no notification. The trip is **late February – early March
2027**, which means the windows start opening around **September 2026**.
Manually re-checking a dozen inns across a two-week window is the job.

The solution is not a booking bot. It is: snapshot the vacancy state of a
shortlist nightly, diff against yesterday, and tell me the moment something
opens — with a one-click `reserveUrl`. The last thirty seconds stay human.

---

## Hard constraints — do not spend time rediscovering these

### APIs that are dead. Do not attempt, do not research, do not work around.

| Source | Status |
|---|---|
| **Jalan Web Service** | Still serves legacy key holders, but **new account registration closed 25 Feb 2020**. We cannot get a key. There is no workaround. |
| **Tabelog** | No public API and never has been. ToS forbids scraping. Every vendor selling a "Tabelog API" is reselling scraped data. We store `tabelog_url` as a link a human opens. That is the whole integration. |
| **Booking / write access** | No Japanese OTA exposes a public write API. Rakuten's real booking API is the B2B *Travel Xchange* product, gated behind a partner contract. Do not design around a write path. Do not suggest browser automation as a substitute. |

If you find yourself designing anything that fetches a Tabelog page or
submits a reservation form, stop and flag it instead.

### APIs that are live and in scope

- **Rakuten Web Service — Travel** (free app ID). `VacantHotelSearch` is the
  load-bearing endpoint. `KeywordHotelSearch` resolves a name → `hotelNo`.
  `GetAreaClass` gives the area code tree. `HotelDetailSearch` for enrichment.
- **GSI (国土地理院) raster tiles** and **OSM/Overpass** — free, keyless, for
  the visualizer layer. Prefer these over paid basemaps.
- **Google Places / Routes** — already wired in Phase 1 for geocoding and
  transit legs. Keep as-is; don't migrate it.

### Rakuten gotchas already paid for in blood

Every one of these is in `rakuten.py`. Do not "simplify" them away.

1. **`accessKey` is required alongside `applicationId`.** Marked NEW in the
   docs; essentially every tutorial online predates it. Missing it returns a
   bare `400 wrong_parameter` with no useful message.
2. **Coordinates default to Tokyo Datum in arc-seconds** — Tokyo Station is
   `latitude=128440.51`. Always send `datumType=1` for WGS84 decimal degrees
   on both input and output.
3. **`searchRadius` is capped at 3.0 km**, minimum 0.1. Not 30.
4. **HTTP 404 `not_found` is data, not an error.** It's the "nothing
   available" state and the transition out of it is the entire product.
   Caveat: Rakuten returns the same 404 for *sold out* and *calendar not yet
   published*. We cannot distinguish them. Say so in the UI rather than
   guessing.
5. **`hotelMinCharge`, `lowestCharge`, `highestCharge` are dead fields** that
   always return 0. Use `dailyCharge.total`.
6. **`dailyCharge` covers only the first night** of a multi-night stay.
7. **`hotelNo` accepts max 15 per call.** Batch aggressively — a dozen inns
   on the same night should cost one request, not twelve.
8. **`reserveRecordCount` counts bookable *plans*, not rooms.** Room-level
   inventory is not exposed. Do not build logic on it.
9. Rakuten throttles repeated identical request URLs. Keep the inter-call
   floor and the 429/503 backoff.

---

## Starting material

Three modules exist as a working reference implementation:

- `rakuten.py` — API client. `Hotel` / `Plan` dataclasses, `vacancy()`,
  `resolve()`, `area_class()`. Handles all nine gotchas above.
- `watch.py` — schema (`watch_target`, `availability_snapshot`), snapshot
  + diff producing `opened` / `closed` / `new_plan` / `price_drop`.
  The diff state machine is tested against a simulated four-day sequence.
- `mcp_server.py` — FastMCP server: `resolve_inn`, `check_availability`,
  `search_lodging`, `add_watch`, `list_watches`, `run_watch`.

Treat these as a **strong starting point, not scripture**. Read them
critically. If the integration into `tp/` wants a different shape, say so in
`PLAN.md` with reasoning. But if you rewrite something, rewrite it because
it's wrong, not because you didn't read it.

---

## The architectural problem I want you to solve in `PLAN.md`

`CLAUDE.md` states: *markdown is canonical, the DB is an ephemeral index,
regenerated by `tp parse`, git versions the markdown, no versioning in the DB.*

**`availability_snapshot` breaks that rule.** It is observational time-series
data about the outside world. It cannot be regenerated from markdown, and
blowing it away on `tp parse` destroys the diff baseline — which is the only
thing that makes the watcher work at all.

Pick an approach and defend it:

- **(a)** A second DB file (`observations.db`) that `tp parse` never touches,
  keeping the ephemerality rule intact for the planning DB.
- **(b)** Amend the rule: mark certain tables as durable and have `tp parse`
  preserve them.
- **(c)** Snapshots as append-only JSONL on disk, DB holds only latest state.
- **(d)** Something better.

I have a mild preference for (a) — clean separation between *my plan* and
*the world's state* — but I'm not attached. Argue for whichever you think is
right.

---

## Scope for this phase

**In:**
- Rakuten client + availability watcher integrated into `tp/`.
- Schema: `place.rakuten_hotel_no`, plus watch/snapshot tables.
- `booking_status` on `place` stops being hand-maintained and becomes derived.
- CLI: `tp watch add|list|run|remove`, consistent with existing typer surface.
- MCP server registered in the repo's `.mcp.json` for project scope.
- A scheduled run (cron or launchd — propose one, note the tradeoff) and some
  way of actually reaching me when something opens. Notification channel is an
  open question; ask me rather than picking.

**Out — explicitly deferred, do not build:**
- The map visualizer upgrade (GSI tiles, availability-coloured pins). Next phase.
- Restaurant APIs. Hot Pepper Gourmet only indexes places that buy Recruit
  advertising — chain izakaya and 宴会 party-plan venues. That is the precise
  inverse of what this trip is about, and wiring it in would pollute the
  dataset with the wrong kind of place. Not "later"; **no**.
- Transit routing beyond what Phase 1 already does. ODPT is Tokyo-weighted and
  much of its good data is licensed only for the duration of the annual Open
  Data Challenge. Not useful for Kyushu/Setouchi.
- Any traveller-profile or recommendation-engine work.

---

## Stack and style

Python, `uv`, `typer`, raw `sqlite3` (no ORM), `httpx`. Match the existing
code's conventions rather than importing your own. Type hints throughout.
Prefer boring, readable, debuggable over clever.

MCP tools must return **compact text, not raw JSON**. Rakuten payloads are
enormous and will eat the context window for no benefit — return the handful
of fields the model will actually reason about, plus a URL for the rest.

---

## How to work

1. Read `CLAUDE.md`, `tp/`, and the three reference modules.
2. Ask me anything genuinely ambiguous **before** planning. One round of
   questions is welcome; don't guess at things I can answer in ten seconds.
3. Write `PLAN.md`: schema changes, module layout, CLI surface, MCP surface,
   your answer to the durability problem, scheduling approach, and a short
   list of anything you think is wrong with the reference implementation.
4. Stop. Wait for approval. Then build.

Push back on anything above that you think is mistaken. I'd rather argue at
the plan stage than unpick it later.
