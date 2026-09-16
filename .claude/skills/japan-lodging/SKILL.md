---
name: japan-lodging
description: Search and shortlist Japanese lodging and restaurants for a trip using the tp MCP tools, applying Patrizio's travel taste. Use when asked to find, compare, or watch ryokan/minshuku/hotels, or to find places to eat for a trip in Japan.
---

# Finding lodging and food in Japan

The `tp` MCP tools are deliberately neutral: they return what Rakuten and Google
say, unfiltered. This skill is the judgement layer. Apply it when helping choose;
never bake it into the tools, and never hide results — say what you're setting
aside and why, so the boring option stays available when it's the right one.

## The traveller

Two people, Patrizio and his sister. Slow, food-deep, sensory travel. He is
Italian, based in Copenhagen, and thinks in kroner — the tools convert yen for
him, so quote both. He would rather have four excellent nights than eight
adequate ones.

## What to prefer

**Countryside: family-run, half-board, onsen.** A minshuku or small ryokan where
dinner and breakfast are included is the point of a rural night — the meal *is*
the experience. Filter with `with_dinner: true`. A 1789 family inn beats a
comfortable modern hotel every time, even at the same price.

**Cities: low-friction and cheap is fine.** Nobody eats dinner at their Tokyo
hotel. In cities, a clean well-located room near a station is doing its whole
job — this is where the chain business hotel is genuinely the right answer, and
saying so is not a failure of taste. Spend the difference on dinner.

**One singular experience per trip.** The thing that can only happen this season,
this year. For February–March 2027 that is already chosen: Omizutori at
Todai-ji, 1–14 March. Don't propose a second — it dilutes the first.

**No redundancy across a trip.** Four kaiseki dinners in twelve days is three
kaiseki dinners too many. Track what the trip already covers and steer toward
what it doesn't. This is the strongest single filter he has: on the Nagoya
trip, kaiseki was cut precisely because four minshuku dinners already covered
that register.

## What to be sceptical of

- **Chain business hotels in the countryside.** In a hot-spring town, a Toyoko
  Inn is a wasted night.
- **High Rakuten review counts as a proxy for quality.** A 4.6 from 300 reviews
  and a 4.6 from 8 reviews are different claims. Say which you're looking at.
- **Google ratings for Japanese restaurants.** Coverage is patchy and the
  ratings skew toward places tourists find. Always offer the Tabelog link and
  say the rating is Google's.
- **"Nothing available" as a fact.** Rakuten returns the same empty answer for
  sold out and for a calendar that has not opened. Six months out at a small
  ryokan, not-yet-open is usually the truth. Offer `watch_add`, don't conclude.

## Working shape

1. **Search** with `find_lodging` (a town, station or temple plus dates) or
   `find_food` (a place plus a dish).
2. **Narrow out loud.** Two or three candidates with a sentence each on why,
   plus what you set aside. Not a wall of twenty.
3. **Keep** the good ones with `shortlist_add_lodging` / `shortlist_add_restaurant`.
   This writes to `trips/<slug>/shortlist.yaml` — cheap, reversible, and it
   survives the conversation.
4. **Watch** anything whose calendar hasn't opened: `watch_add`, with a window
   (`window_start`, `window_end`, `nights`) while dates are still moving.
5. **Promote** what he commits to with `shortlist_promote`, then call
   `sync_trip` so the generated index sees `places.yaml` before the next map.

Booking is always his. Every recommendation ends with a URL he opens himself —
there is no write path to any Japanese booking system, and building one is out
of scope permanently.

## This trip

`japan-2027-02`: 18–19 nights, late Feb into early March, two travellers.
Tokyo 4 / Kyoto 2 / Osaka 3 / Hiroshima 2 / Fukuoka 2 / Nara 1, plus 2 nights
countryside ryokan and 2–3 more countryside nights undecided.

- **Nara is urgent.** The night must fall inside 1–14 March for Omizutori, the
  town has little lodging, and that is its busiest fortnight. Watch it first.
- **Countryside slots are open.** Wanted for scenery, temples, onsen. Kinosaki
  Onsen (crab season to ~20 March, seven public baths, walkable in yukata) fits
  the Kansai side; Kurokawa or Yufuin fit the Kyushu side near Fukuoka.
- **Plum, not cherry.** Late February is ume season — Dazaifu Tenmangū is 40
  minutes from Fukuoka.
- **No budget set.** Leave price filters off until he sets one; don't invent a
  ceiling.
