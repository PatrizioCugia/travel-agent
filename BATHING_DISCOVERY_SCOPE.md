# Bathing discovery scope

The planner must distinguish three questions that public map data cannot answer
by itself: which baths exist, whether a specific public bath is currently
visit-able, and whether its tattoo policy permits entry. A missing OSM feature
is a data-coverage gap, never evidence that a bath is absent.

## Implemented first slice

- `discover_nearby("城崎温泉", "onsen")` first checks the reviewed Japanese
  destination/operator directory before requesting Google geocoding or OSM.
- The Kinosaki directory carries the seven named public baths, the official
  Japanese source URLs, a review date, and a conservative day-use state. It
  marks `さとの湯` as temporarily closed rather than treating the town-wide
  tattoo rule as proof it can be visited.
- `bathing_access("地蔵湯")` remains the separate, source-linked policy check.
  A destination-wide rule never applies to baths inside a ryokan.

## Source hierarchy

1. The named facility's current Japanese operator page determines current
   hours, closure, admissions, and private-bath terms.
2. An official Japanese destination association or municipality can enumerate
   shared public baths and state a policy whose scope explicitly names them.
3. OSM is a geographic discovery source only. It adds breadth, but may omit a
   facility or use a different tag.
4. Community directories and reviews can create a research lead, never a
   final tattoo or operating-status assertion.

## Extension contract

Add an area only after reviewing an official Japanese source. Record the
authority, directory URL, current-status URL, local facility names, aliases,
review date, and one of `listed`, `temporarily_closed`, or `unknown` for day
use. Do not scrape pages or manufacture coordinates to make a source fit the
map-candidate model. Refresh the record when the operator changes its page.

The next useful areas are remote Kansai onsen towns selected from actual trip
shortlists. Each should receive an official directory record and separate
facility-policy evidence, rather than a broad unverified national list.
