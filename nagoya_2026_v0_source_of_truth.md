# Nagoya 2026 — Trip Source of Truth (v0 input)

**Purpose**: This document is the canonical reference for the Nagoya November 2026 trip. It is the v0 input for the `travel-planner` project. Migrate from this document into `places.yaml`, `trip.md`, and the day-by-day structure defined in CLAUDE.md.

**Status**: Trip planned, not yet booked. Specific dates TBD.

---

## Trip scope

- **Dates**: November 2026 (specific dates TBD; target mid-to-late November for Korankei peak autumn foliage; ideally include 4th Friday Nov 27 for Nayabashi Yoichi night market)
- **Duration**: 11 nights / 12 days
- **Structure**: 7 nights Nagoya + 2 nights Tsumago + 2 nights Okuhida
- **Total budget**: ~25,400 kr / ~€3,400
- **Themes**: autumn, food-deep, craft-villages, slow-pace, slow-immersive, singular-experience-per-trip
- **Traveler**: solo
- **Origin/return**: open-jaw flight CPH → NGO, KIX → CPH

### Single sentence trip thesis

Nagoya base for 7 days of dense food-and-craft urban exploration, contrasted against 4 nights of rural minshuku in preserved Edo post town (Tsumago) and mountain onsen (Okuhida), with peak November Korankei autumn maples + night illumination as the singular seasonal experience.

---

## Budget breakdown (~25,400 kr)

| Category | Amount (kr) |
|---|---|
| Flights CPH↔NGO/KIX (open-jaw) | 5,800 |
| Anshin Oyado Sakae (7 nights, 1,860/night) | 13,020 |
| Maruya Tsumago minshuku (2 nights, 970/night, dinner+breakfast) | 1,940 |
| Yamano-iori Okuhida minshuku (2 nights, 1,130/night, dinner+breakfast) | 2,260 |
| Food in Nagoya (dinners, lunches, snacks, breakfasts not at minshuku) | ~4,300 |
| Transport (intra-Nagoya + day trips + Shinkansen + Wide View Hida) | ~800 |
| Activities + bars + dessert stops | ~600 |
| Souvenirs | 6,430 |
| Contingency / customs duty | ~250 |

Savings plan: ~700 kr/week from mid-May to departure (~26-29 weeks), bridged by ~8,000 kr ferie penge during trip.

---

## Itinerary structure

| Day | Location | Theme |
|---|---|---|
| 1 | Nagoya (arrival) | Light curry udon dinner, settle in |
| 2 | Nagoya | Atsuta + Tokugawa history day → izakaya → whisky bar |
| 3 | Tokoname day trip + Nagoya | Pottery village → miso-nikomi dinner |
| 4 | Nagoya in-city | Seafood breakfast → river walk → omakase sushi |
| 5 | Seki day trip + Nagoya | Knife village → premium izakaya → optional second-stop |
| 6 | Nagoya in-city | Kissaten breakfast → Osu shopping (manga + vintage) → yakiniku |
| 7 | Korankei day trip + Nagoya | **THE singular November-only autumn maple experience + night illumination + free flexible evening** |
| 8 | Hikone + transit | Half-day castle + Omi beef → Shinano to Nakatsugawa → bus to Tsumago |
| 9 | Tsumago | Magome → Tsumago Nakasendo hike (8 km) → Maruya dinner |
| 10 | Tsumago → Okuhida | Wide View Hida train (2.5h) with bento → Yamano-iori arrival |
| 11 | Okuhida | Shinhotaka Ropeway morning + onsen hopping afternoon |
| 12 | Okuhida → KIX departure | Wide View Hida back → KIX (bento on train: Hida-gyu thermal) |

---

## All places mentioned (the canonical place list for v0)

Organize by category. Each place gets a stable slug, name (EN + local), category, address/location, primary trip day(s), and time slot. This is the canonical place list that gets ported to `places.yaml`.

---

### Accommodations (3)

| Slug | Name (EN) | Name (local) | Category | City | Days | Notes |
|---|---|---|---|---|---|---|
| anshin-oyado-sakae | Anshin Oyado Premier Sakae | 安心お宿プレミア栄店 | accommodation | Nagoya | 1-8 | Premium capsule hotel, onsen, free curry/ramen lobby snacks, ~1,860 kr/night |
| maruya-tsumago | Maruya | 丸屋 | accommodation | Tsumago | 8-10 | Minshuku since 1789, dinner+breakfast included, ~970 kr/night |
| yamano-iori-hotaka-so | Yamano-iori Hotaka-so | 山の庵 穂高荘 | accommodation | Okuhida (Shin-Hirayu) | 10-12 | Mountain minshuku, dinner+breakfast included, ~1,130 kr/night |

---

### Restaurants — Nagoya (planned dinners + lunches)

| Slug | Name (EN) | Name (local) | Category | Subcategory | Address/Area | Day | Time | Notes |
|---|---|---|---|---|---|---|---|---|
| wakashachiya | Wakashachiya | 若鯱家 | restaurant | curry-udon | Nagoya Station / Sakae locations | 1 | dinner | Nagoya curry udon, light arrival dinner |
| atsuta-houraiken-honten | Atsuta Houraiken main shop | あつた蓬莱軒 本店 | restaurant | hitsumabushi | 503 Godo-cho, Atsuta-ku | 2 | brunch | The 1873 inventor of hitsumabushi, walk-in 30-60 min wait Sat/Sun. Tabelog: https://tabelog.com/en/aichi/A2301/A230112/23000063/ |
| atsuta-houraiken-jinguten | Atsuta Houraiken Jingu-ten | あつた蓬莱軒 神宮店 | restaurant | hitsumabushi | Near Atsuta Jingu | 2 | brunch alt | Alternate Houraiken location if main shop full. Tabelog: https://tabelog.com/en/aichi/A2301/A230112/23000109/ |
| hamasho-nishiki | Hamasho Nishiki Honten | 浜匠 錦本店 | restaurant | izakaya-cochin | B1F, 3-15-1 Nishiki, Naka-ku | 2 | dinner | Nagoya Cochin yakitori, tebasaki, doteni, ~¥5,000-7,000 |
| yamamotoya-honten-esca | Yamamotoya Honten ESCA | 山本屋本店 エスカ店 | restaurant | miso-nikomi-udon | B1F ESCA, Nagoya Station underground | 3 | dinner | Miso-nikomi udon in Kakukyu hatcho miso broth, ~¥1,500-2,000. Tabelog: https://tabelog.com/en/aichi/A2301/A230101/23000123/ |
| kanazawa-maimon-sushi | Kanazawa Maimon Sushi | 金沢まいもん寿司 | restaurant | sushi-kaiten | Sakae area | 4 | lunch | Kaiten sushi lunch, premium Sea of Japan fish, ~¥3,000-5,000 |
| sushi-okimuraya | Sushi Okimuraya | 鮨 沖村屋 | restaurant | sushi-omakase | 1-14-44 Higashi-sakura, Higashi-ku | 4 | dinner | Edomae omakase dinner, ~¥15,000, book 3-4 weeks ahead |
| sakana-no-hachibei | Sakana no Hachibei Yabacho | 魚の八兵衛 矢場町 | restaurant | izakaya-premium | Yabacho area | 5 | dinner | Premium seafood izakaya, ~¥6,000-8,000, book 1-2 weeks ahead |
| mitsumura-tempura | Tempura Kakiage Mitsumura | 天ぷら かきあげ 三村 | restaurant | tempura | Imaike area | 6 | lunch | Tempura specialist, 50-year sauce, ~¥2,500-3,500 |
| setsugekka-tanaka-satoru | Setsugekka Tanaka Satoru | 雪月花 田中悟 | restaurant | yakiniku | Sakae area | 6 | dinner | Tabelog Award Bronze 2024-2026, premium yakiniku, ~¥10,000-15,000, book 3-4 weeks ahead. Tabelog: https://tabelog.com/en/aichi/A2301/A230103/23071686/ |
| gomitori | Gomitori (Museum Izakaya) | 伍味酉 本店 | restaurant | izakaya-late-night | 3-15-6 Sakae, Naka-ku | 5/7 | optional late dinner | 1956 historic late-night izakaya, full Nagoya-meshi canon, open until 5am, ~¥3,000-5,000 |

---

### Restaurants — Day trips

| Slug | Name (EN) | Category | Subcategory | City | Day | Time | Notes |
|---|---|---|---|---|---|---|---|
| tokoname-local-lunch | Tokoname pottery walk lunch | restaurant | local-flexible | Tokoname | 3 | lunch | Walk-in seafood or local on Pottery Footpath, ~¥1,500-2,500 |
| seki-local-lunch | Seki knife town lunch | restaurant | local-flexible | Seki | 5 | lunch | Soba or eel near Hamono Museum, ~¥1,500-2,500 |
| korankei-village-lunch | Korankei village lunch | restaurant | local-flexible | Korankei (Asuke) | 7 | lunch | Sansai soba or gohei-mochi set near Taigetsu Bridge, ~¥2,000-2,500 |
| korankei-village-stalls | Korankei village food stalls | restaurant | street-food | Korankei (Asuke) | 7 | dinner | Illumination-season stalls: gohei-mochi, yakitori, hot sake, ~¥1,500-2,500 |
| hikone-omi-beef | Hikone Omi beef restaurant | restaurant | wagyu | Hikone | 8 | lunch | Senmaru (千丸) or Kaneki (かねき) along Yume Kyobashi Castle Road, ~¥3,500-5,500 |

---

### Bars and night spots

| Slug | Name (EN) | Name (local) | Category | Subcategory | Address/Area | Day | Time | Notes |
|---|---|---|---|---|---|---|---|---|
| bar-barns | Bar Barns | バー バーンズ | bar | whisky-cocktail | Nishiki area, Fushimi | 2 | night | Speakeasy whisky + cocktail bar, owner-bartender Toru Hirai, ~¥1,500-2,500 per drink. Tabelog: https://tabelog.com/en/aichi/A2301/A230102/23000103/ |
| sake-stand-sabou | Sake Stand Sabou | 酒場 茶房 | bar | sake-standing | Sakae area | 4 | afternoon | Daytime sake standing bar |
| bar-hasegawa | Bar Hasegawa | バー長谷川 | bar | classic-cocktail | Sakae | 5 | night (optional) | Classic cocktail bar (alternative to Hachibei extension) |
| bar-lumina | Bar Lumina | バー ルミナ | bar | cocktail | Sakae | 5 | night (alt) | Alternative to Hasegawa |
| zenkoku-meishu-izakaya | Zenkoku Meishu Izakaya | 全国銘酒居酒屋 | bar | sake-izakaya | Sakae | 6 | night | 100+ Aichi sake list, English menu |
| pettegola | PETTEGOLA | ペッテゴラ | bar | shime-parfait | near Fushimi | 5 | night (alt) | Authentic Sapporo-style shime parfait bar, Tue-Thu 19:00-23:00, Fri/Sat 19:00-24:00 |

---

### Cafés, kissaten, matcha, dessert

| Slug | Name (EN) | Name (local) | Category | Subcategory | Address/Area | Day | Time | Notes |
|---|---|---|---|---|---|---|---|---|
| konparu-kissaten | Konparu | コンパル | café | kissaten | Sakae | 6 | breakfast | Classic Nagoya kissaten breakfast, ogura toast |
| komeda-coffee | Komeda's Coffee Nishiki Isemachitori | コメダ珈琲店 錦伊勢町通店 | café | kissaten-chain | Sakae | 6 | afternoon | 1968 Nagoya-origin coffee chain, red velvet sofa interior |
| trunk-coffee | Trunk Coffee | トランクコーヒー | café | third-wave | near Horikawa | 4 | afternoon | Third-wave specialty coffee |
| ryoguchiya-tokugawa | Ryoguchiya Korekiyo at Tokugawa Art Museum | 両口屋是清 | café | wagashi-traditional | Tokugawa Art Museum | 2 | afternoon | 1634 Owari Tokugawa wagashi purveyor counter inside museum |
| masuhan-chaten | Masuhan Chaten | 増半茶店 | café | matcha-shop | Fushimi | 6 | afternoon | 1840 historic tea shop, reopened 2023, matcha ice cream + hojicha latte |
| kawabun | Kawabun Ultimate Matcha Parfait | 川文 | café | matcha-parfait | 2-12-19 Marunouchi, Naka-ku | 4 | afternoon | Nagoya's 400-year-old restaurant, seven-matcha tasting parfait, weekdays only 13:00-17:30. Replaces Saijoen on Day 4. |
| saijoen-matcha-cafe | Saijoen Matcha Cafe | 西条園抹茶カフェ | café | matcha-modern | Dai Nagoya Building B1F | (backup) | — | Chez Shibata patissier collaboration, Nishio matcha. Backup if Kawabun closed. |
| aoyagi-sohonke-kitte | Aoyagi Sohonke at KITTE Nagoya | 青柳総本家 KITTE名古屋 | café | uirou-matcha | KITTE Nagoya 1F | 8 | morning option | 1879 uirou maker sit-down counter, matcha + uirou sets, daily 10:00-21:00 |
| 25-ji-made-ice | 25時までアイス | 25時までアイス | café | shime-parfait-takeout | Tomiya Bldg 1F, 4-17-24 Sakae | 6 | post-yakiniku night | Takeout late-night parfait, 17:00-25:00, alcohol options |

---

### Sights, shrines, temples, gardens, museums

| Slug | Name (EN) | Name (local) | Category | Subcategory | Address/Area | Day | Time | Notes |
|---|---|---|---|---|---|---|---|---|
| atsuta-jingu | Atsuta Jingu | 熱田神宮 | shrine | major | Atsuta-ku | 2 | morning | One of Japan's most sacred shrines, home of Kusanagi sword |
| tokugawa-en | Tokugawa-en Garden | 徳川園 | garden | edo-period | Higashi-ku | 2 | afternoon | Edo-period garden, peak November autumn foliage, ~¥300 entry |
| tokugawa-art-museum | Tokugawa Art Museum | 徳川美術館 | museum | art | Higashi-ku | 2 | afternoon | Owari Tokugawa family treasures, ~¥1,400 |
| shirakabe-samurai-district | Shirakabe samurai district walk | 白壁 | sight | walking-district | Shirakabe area | 2 | afternoon | Preserved samurai quarter, ~60 min walking |
| horikawa-river-walk | Horikawa river walk | 堀川 | sight | walking-district | Central Nagoya | 4 | morning | River walk between Nayabashi and Nishikibashi |
| shikemichi-district | Shikemichi historical district | 四間道 | sight | walking-district | North of Nagoya Station | 4 | morning | Preserved merchant district with black-walled storehouses |
| yanagibashi-market | Yanagibashi Market | 柳橋中央市場 | market | seafood-wholesale | Near Nagoya Station | 4 | morning | Nagoya's seafood wholesale market, Maguroya Kurogin breakfast spot |
| osu-kannon | Osu Kannon Temple | 大須観音 | temple | major | Osu | 6 | morning | Osu's main temple, gateway to Osu shopping arcade |
| osu-antique-market | Osu antique market | 大須骨董市 | market | antique | Osu Kannon grounds | 6 (if 18th or 28th) | morning | Monthly antique market on 18th and 28th of each month |
| korankei-gorge | Korankei Gorge | 香嵐渓 | sight | autumn-foliage | Asuke, Toyota City | 7 | full day | 4,000 maples, 400-year-old trees, November illumination 17:00-21:00. THE singular November experience. |
| kojakuji-temple | Kojakuji Temple | 香積寺 | temple | korankei | Korankei | 7 | afternoon | Temple in Korankei with panoramic gorge views |
| taigetsu-bridge | Taigetsu Bridge | 待月橋 | sight | iconic-bridge | Korankei | 7 | morning | Iconic red bridge over Tomoe River in Korankei |
| hikone-castle | Hikone Castle | 彦根城 | sight | original-castle | Hikone | 8 | morning | One of Japan's 12 original castle keeps, National Treasure, ~¥800 |
| genkyu-en | Genkyu-en Garden | 玄宮園 | garden | castle-garden | Hikone | 8 | morning | Castle garden adjacent to Hikone Castle |
| nakasendo-trail | Nakasendo Magome-Tsumago trail | 中山道 | sight | preserved-trail | Kiso Valley | 9 | full day | 8 km preserved post-town trail, ~3 hours hike |
| waki-honjin-okuya | Waki-honjin Okuya Museum | 脇本陣奥谷 | museum | edo-period | Tsumago | 9 | afternoon | 1877 secondary inn for daimyo, ~¥600 |
| tsumago-honjin | Tsumago Honjin Museum | 妻籠本陣 | museum | edo-period | Tsumago | 9 | afternoon | Reconstructed main inn, ~¥300 |
| otsumago | Otsumago | 大妻籠 | sight | preserved-village | South of Tsumago | 9 | late afternoon | Smaller preserved post-town settlement, 30 min walk from Tsumago |
| shinhotaka-ropeway | Shinhotaka Ropeway | 新穂高ロープウェイ | ropeway | alpine | Shin-Hotaka, Okuhida | 11 | morning | Japan's only double-decker cable car, 1,117m to 2,156m, Northern Alps panorama, ~¥3,300 round trip |
| hirayu-falls | Hirayu Falls | 平湯大滝 | sight | waterfall | Hirayu Onsen, Okuhida | 11 | optional | 64m waterfall, 30 min walk from Hirayu Onsen center |

---

### Day trip destinations (cities/regions, not single pins)

| Slug | Name (EN) | Name (local) | Category | Day | Notes |
|---|---|---|---|---|---|
| tokoname | Tokoname | 常滑 | sight | 3 | Pottery village 60 min from Nagoya, Pottery Footpath, maneki-neko walk, kyusu/yunomi sourcing |
| seki | Seki | 関 | sight | 5 | Knife village, Seki Hamono Museum, Cutlery Hall, knife purchases (gyuto + petty) |
| hikone | Hikone | 彦根 | sight | 8 | National Treasure castle + Omi beef + Yume Kyobashi Castle Road |
| nakatsugawa | Nakatsugawa | 中津川 | transit | 8 | JR transit point Nagoya → Tsumago route, Shinano train terminus before bus |
| magome | Magome | 馬籠 | sight | 9 | Sister post town to Tsumago, start of Nakasendo hike |
| hirayu-onsen | Hirayu Onsen | 平湯温泉 | onsen | 10-12 | Central Okuhida onsen village, bus hub for the 5 Okuhida villages |
| shin-hirayu-onsen | Shin-Hirayu Onsen | 新平湯温泉 | onsen | 10-12 | The Okuhida village where Yamano-iori is located |

---

### Shops and souvenir sources

| Slug | Name (EN) | Category | Subcategory | Address/Area | Day | Notes |
|---|---|---|---|---|---|---|
| sankodo-pens | Sankodo Sakae | shop | stationery | Sakae | 4 | Pen specialist for Tombow Zoom 707, Sakura Craft Lab 002 |
| takashimaya-depachika | Takashimaya Gates Tower depachika | shop | depachika | Nagoya Station Gates Tower B1F | (multi) | Premium food hall, premium ekiben for Day 8 Bento #1, Mino-yaki sourcing |
| matsuzakaya-depachika | Matsuzakaya Sakae depachika | shop | depachika | Sakae | (multi) | Department store food hall, Mino-yaki ceramics sourcing |
| mitsukoshi-sakae | Mitsukoshi Sakae | shop | depachika | Sakae | (multi) | Department store, Oribe + Shino style Mino-yaki |
| mandarake-osu | Mandarake Nagoya | shop | manga | Osu | 6 | Manga + action figures, vintage manga |
| animate-osu | Animate Osu | shop | manga | Osu | 6 | Mainstream manga/anime merchandise |
| komehyo-osu | Komehyo Honkan | shop | vintage-secondhand | Osu | 6 | 7-floor secondhand flagship, Floor 4 vintage clothing including denim |
| unwave-osu | Unwave | shop | vintage-workwear | Osu arcade 2F | 6 | Vintage Levi's specialist + military + workwear |
| archaic-osu | Archaic | shop | vintage-high-end | Osu | 6 | Museum-quality 1940s+ vintage, French moleskin + US/UK military |
| crout-osu | CROUT | shop | vintage-broad | Osu (also Sakae location) | 6 | Wide-range vintage, denim-heavy 2nd floor |
| seki-hamono-museum-shop | Seki Hamono Museum knife shops | shop | knives | Seki | 5 | Knife purchases, gyuto + petty |
| tokoname-pottery-studios | Tokoname pottery studios | shop | pottery | Tokoname | 3 | Kyusu + yunomi sourcing, INAX showrooms |

---

### Stations, transit hubs

| Slug | Name (EN) | Name (local) | Category | Notes |
|---|---|---|---|---|
| nagoya-station | Nagoya Station | 名古屋駅 | transit | Main hub, Shinkansen + JR Chuo + Meitetsu + Meijo subway |
| sakae-station | Sakae Station | 栄駅 | transit | Sakae subway hub, Higashiyama + Meijo lines |
| meitetsu-bus-center | Meitetsu Bus Center | 名鉄バスセンター | transit | Bus to Korankei (Day 7) |
| nakatsugawa-station | Nakatsugawa Station | 中津川駅 | transit | Day 8 Shinano endpoint, bus to Tsumago |
| takayama-station | Takayama Station | 高山駅 | transit | Wide View Hida transit, Day 10 and Day 12 |
| kansai-airport-kix | Kansai International Airport (KIX) | 関西国際空港 | transit | Day 12 departure |
| nagoya-airport-ngo | Chubu Centrair International Airport (NGO) | 中部国際空港 | transit | Day 1 arrival |

---

## Special note: places with date-specific availability

- **Osu antique market**: 18th and 28th of each month. Day 6 plan benefits if dates align.
- **Nayabashi Yoichi night market**: 4th Friday of each month. Likely Nov 27, 2026. Day 7 evening replacement if dates align.
- **Korankei night illumination**: typically Nov 15-30 peak. Confirm dates before booking.
- **Kawabun matcha parfait**: weekdays only 13:00-17:30. Day 4 needs to be a weekday.
- **Maruya Tsumago**: book 6-8 weeks ahead (September).
- **Yamano-iori Okuhida**: book 6-8 weeks ahead (September).
- **Sushi Okimuraya, Setsugekka, Sakana no Hachibei, Bar Barns**: book 1-4 weeks ahead.

---

## Souvenir planning (~6,430 kr)

Not all single-location entries but they need to map to source places:

**For others (~1,740 kr)**:
- Brother: Tombow Zoom 707 ballpoint (Sankodo Sakae)
- Sister: @cosme skincare bundle + furoshiki (Sakae depachika)
- Mom: furoshiki + lacquer plate (depachika)
- Dad: tenugui + Tokoname sake cup (Tokoname Day 3)
- Grandma: Tokoname tea cup + Ryoguchiya Sasaragata box (Tokoname + Ryoguchiya)

**For Patrizio (~4,690 kr)**:
- Sakura Craft Lab 002 (Sankodo)
- Mino washi + Mnemosyne notebook + Tomoe River pad (Sankodo + depachika)
- Vintage haori (Komehyo Osu)
- 5 omamori (Atsuta Jingu)
- 1 whisky bottle (~¥7,000, depachika)
- 1 shochu bottle (~¥2,500, depachika)
- 2 matcha tins (depachika)
- 2 Seki knives — gyuto + petty (Seki Day 5)
- 2 posters
- Kyusu + yunomi (Tokoname Day 3)
- 2 action figures (Mandarake Osu)
- Antique from Osu market (Day 6 if 18th/28th aligns)
- Vintage workwear discretionary (Unwave / CROUT / Archaic ~1,500 kr)

---

## Trains and bentos (Day 8, 10, 12)

Three premium ekiben planned:
- **Bento #1** (Day 8 Shinano Nagoya → Nakatsugawa, 50 min): Premium depachika bento from Takashimaya — Tsukiji Tamura kaiseki or Nadaman washoku, ¥3,500
- **Bento #2** (Day 10 Wide View Hida Nagiso → Takayama, 2.5h): Cochin chicken bento
- **Bento #3** (Day 12 Wide View Hida Takayama → Nagoya, 2.5h): Hida-gyu thermal bento

---

## Critical decisions already made (don't relitigate)

1. **Korankei replaces Tajimi as Day 7 day trip** — peak November autumn maples + night illumination, singular November experience
2. **Houraiken Bekkan kaiseki REMOVED** — four minshuku dinners (Maruya x2 + Yamano-iori x2) already cover the multi-course traditional Japanese register; redundant
3. **Mino-yaki sourced at Nagoya depachika** (not via Tajimi day trip)
4. **Day 1 arrival dinner**: Wakashachiya curry udon (changed from earlier Tachinomi Uotsubaki plan)
5. **Kawabun replaces Saijoen on Day 4** for matcha-depth via seven-matcha tasting parfait
6. **Trip structure locked**: 7 nights Nagoya + 2 Tsumago + 2 Okuhida = 11 nights
7. **Open-jaw flight**: arrive NGO, depart KIX
8. **No Hiroshima / Nagasaki / Ehime** — saved for future trip 2028

---

## Existing planning documents (source material for migration)

The following markdown documents exist as prose source material:

1. `japan_trip_2026_planning.md` — main planning overview with budget, lodging, transport, souvenirs
2. `japan_trip_2026_nagoya_plan.md` — Nagoya day-by-day with hour-by-hour schedules
3. `japan_trip_2026_food_plan.md` — comprehensive meal plan, snacks, breakfasts, bentos
4. `japan_trip_2026_restaurants.md` — restaurant details with Tabelog links
5. `japan_trip_2026_phrases.md` — Japanese phrases reference
6. `japan_trip_2026_late_night_food.md` — yokocho, yatai, late izakaya, shime parfait

These will be migrated into the `trips/nagoya-2026-11/` directory structure per the CLAUDE.md spec.

---

## Trip's "singular experiences" (the can-only-happen-this-trip filter)

- **Korankei autumn maples + night illumination** (mid-late November only; future trips different season = different forest)
- **Maruya Tsumago minshuku** (preserved 1789 Edo post-town inn; possible to repeat but tied to this trip's Edo Japan theme)
- **Yamano-iori Okuhida onsen-minshuku** (Northern Japanese Alps mountain onsen; could repeat in future)
- **Day 1 arrival "first day in Japan" novelty** (trip-specific)
- **Nayabashi Yoichi night market on Nov 27** (date-specific, monthly)
- **Osu antique market on 18th or 28th** (date-specific, monthly)

---

## Outstanding open questions (pre-trip)

1. Lock specific arrival/departure dates (target mid-late November, weekday Day 4 for Kawabun, ideally align Day 6 with Osu market 18th/28th, Day 7 with Nayabashi 4th Friday Nov 27)
2. Book flights (late July target for price optimization)
3. Confirm Korankei illumination dates for 2026
4. Verify Kakukyu / Maruya miso brewery operating hours if Okazaki day trip is added
5. Book minshuku (September target, 6-8 weeks ahead)
6. Book restaurants (October target, 3-4 weeks ahead)

---

*This document is the v0 source of truth for migrating the Nagoya 2026 trip into the travel-planner project. Once migration is complete, the canonical structured data lives in `trips/nagoya-2026-11/places.yaml` + `trip.md` + `days/*.md`. This document then becomes a historical reference.*

*Document version: 1.0*
*Last updated: at v0 bootstrap*
