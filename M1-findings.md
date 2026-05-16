# M1 findings

Output of M1's two-Opus research team. Drives M3 (places lookup) and M5 (output generators). Source-cited; nothing fabricated.

## Decisions taken from the research

### Places lookup (M3)

- **Use Places API (New)** — the legacy Places API is closed to new projects since 2024. Endpoint: `POST https://places.googleapis.com/v1/places:searchText` with a JSON body, `X-Goog-Api-Key` header, and an `X-Goog-FieldMask` header. Implemented in `src/travel_planner/maps/places_lookup.py`.
- **Field mask** (cost-sensitive): `places.id,places.displayName,places.formattedAddress,places.location,places.types,places.rating,places.userRatingCount,places.businessStatus`. This keeps us in Pro tier (5k free/month) + the rating fields in Enterprise (1k free/month). Avoid `places.reviews` / `places.photos` (Atmosphere SKU, paid).
- **Query strategy** (M3 fallback chain): `(name_local + address, lang=ja)` → `(name_en + address, ja)` → `(name_local, ja)` → `(name_en + " Nagoya", en)`. Stop at the first attempt that returns confidence ≥ 0.6.
- **Location bias**: `locationBias.circle` at Nagoya (35.18, 136.91, radius 25 km). Use `locationBias` (soft nudge), not `locationRestriction` (hard filter — produces false zero-results near the edge).
- **Disambiguation** (multi-candidate, e.g. Atsuta Houraiken's 3 branches): set `pageSize: 5`, score candidates by (a) normalized address token overlap, (b) `businessStatus == "OPERATIONAL"`, (c) `userRatingCount` as tiebreaker. Require gap > 10% over #2 to accept. Below the threshold → write to `output/lookup-misses.md` instead of mutating `places.yaml`.
- **Round-trip back into `places.yaml`**: ruamel.yaml (not PyYAML) to preserve key order, comments, and block-scalar style. Never overwrite a hand-set `lat`/`lng`/`google_place_id` without an explicit `--force`. Write a hidden `_lookup_meta` key (confidence, query_used, timestamp, formatted_address) for audit.
- **Caching**: persist `(query, language) → response` on disk keyed by trip place `id`. Re-running `tp parse` should never re-hit the API for already-filled places.

### Output artifacts (M5)

- **`my-maps.csv` columns** (in this order): `name, latitude, longitude, address, category, day, time_slot, description, website, tabelog_url, google_place_id`. UTF-8 **no BOM**, LF newlines, RFC-4180 quoting (doubled quotes inside, embedded `\n` inside quoted multi-line cells).
- **Why lat/lng + address both**: provide lat/lng so the user picks them as the location columns at import → My Maps skips the geocoder entirely. Address remains as metadata in the info card. Skipping the geocoder is critical for Japanese addresses where the geocoder is unreliable.
- **Pin styling**: no column controls pin color/icon at CSV-import time. Post-import, "Style by data column → `category`" produces consistent styling, and the rule persists across CSV re-imports (My Maps remembers the styling-column). Document this in `trips/<slug>/output/README.md`.
- **KML alongside CSV**: emit `output/my-maps.kml` with `<Style>` per-category icons + `<Folder>` per day. Lets a fresh import skip the post-import styling click. CSV stays canonical (round-trips style rules on re-import); KML is the styling-baked-in alternative. Sub-5 MB easily at our scale.
- **`saveable-places.md`**: markdown bullets, one per place: `[name — open in Maps](https://www.google.com/maps/search/?api=1&query=<encoded+name>&query_place_id=<ID>)` with a sub-line `name_local · category · day · time_slot`. Group by category, then by day. Tap on mobile → Maps app → Save. The documented `search/?api=1&query_place_id=` form is more reliable than the older `?q=place_id:` form.
- **Daily-route URLs** (`daily-routes.md`): `https://www.google.com/maps/dir/?api=1&waypoints=place_id:A|place_id:B|...&travelmode=walking`. Use `place_id:<ID>` form (not free-text) to avoid geocoder drift. Cap: **9 waypoints desktop, 3 mobile**; for days with more, split into multiple URLs. URL must stay under 2,048 chars total.
- **Limits**: 2,000 rows / 10 layers / 10,000 features per My Maps map; 40 MB CSV / 5 MB KML. No issue at our trip scale (~50 places).

### Spike (this milestone)

`tp spike` writes a 1-row CSV with the M5-recommended schema. Validates the column ordering and UTF-8 encoding work in the wild. Run requires `GOOGLE_MAPS_API_KEY`.

## Sources

### Agent A (CSV format)
- [Import map features from a file — My Maps Help](https://support.google.com/mymaps/answer/3024836)
- [Google MyMaps invalid CSVs when using commas and newlines](https://support.google.com/maps/thread/321019238)
- [Can a .csv import control color/icon of pins?](https://support.google.com/maps/thread/128513887)
- [Google Maps URLs (Get Started)](https://developers.google.com/maps/documentation/urls/get-started)
- [Direct Users to Google Maps with Maps URL or Places API](https://developers.google.com/maps/architecture/maps-url)
- [Import KML into Google Earth](https://developers.google.com/maps/documentation/earth/import-kml)
- [Why Google My Maps Has a 2,000 Location Limit](https://notiontomaps.com/blog/google-my-maps-2000-location-limit)
- [Google Placemarks From Spreadsheets — Michael Minn](https://michaelminn.net/tutorials/google-csv/)

### Agent B (Places API)
- [Places API (New) Text Search](https://developers.google.com/maps/documentation/places/web-service/text-search)
- [Places API (New) overview](https://developers.google.com/maps/documentation/places/web-service/op-overview)
- [Places API usage and billing](https://developers.google.com/maps/documentation/places/web-service/usage-and-billing)
- [Migrate from Legacy Find Place / Text Search](https://developers.google.com/maps/documentation/places/web-service/legacy/migrate-text)
- [Places API best practices](https://developers.google.com/maps/documentation/places/web-service/web-services-best-practices)
- [Japan address format spec (Google)](https://developers.google.com/my-business/content/japan-address-format-spec)
- [Google Places API pricing 2026 breakdown](https://www.boundev.ai/blog/google-maps-api-pricing-guide)

## Empirical validation still pending

- **`tp spike` against live API** — blocked on `GOOGLE_MAPS_API_KEY`. When provided, the spike will confirm: (a) the New API call shape works, (b) the field-mask returns what we expect, (c) lat/lng land where Patrizio recognizes them, (d) the CSV imports cleanly with `name`/`latitude`/`longitude` as the wizard picks, (e) Japanese info-card text renders correctly.
- **Manual My Maps import of the spike CSV** — Patrizio's read on the resulting pin will tell us if any of the agent's claims (no BOM, RFC-4180 quoting, etc.) need adjustment before M5.

## Carry-over to BACKLOG.md (decided)

KML output and `saveable-places.md` move from "phase-1 stretch" to "M5 scope." Both are small additions to the generator and pay back the wall-clock cost of the research many times over.
