# Photography Hotspot Finder — Design

## Concept
A recommendation tool that scores city neighborhoods/locations by "photogenicity"
and suggests where to shoot based on a user's stated preferences (scenery type,
time of day, crowd tolerance). Results render on a map. Chosen over a pure
exploration map to (a) avoid repeating Project A's dashboard, (b) demonstrate a
product/decision-engine story for AI PM roles, and (c) exercise dynamic SQL harder.

## Scope
- **City:** Tokyo first (personal ground truth from recent trip; dense Flickr
  coverage). Built city-agnostic — city is a config value + a column, never
  hardcoded. Second city (one of Project A's five) optional if time allows.
- **Data sources:** Flickr API (geotagged photos, tags, engagement, timestamps),
  Google Places (place types, ratings, popular times), weather API (provider TBD —
  likely Open-Meteo, no key needed).

## Scoring dimensions
Split into two groups — this split *is* the schema.

### Intrinsic (static, per location)
- **Photogenicity** (base score, not a user filter): Flickr photo density +
  engagement (favorites/views per photo) + Google rating. Precomputed, stored as
  one column, ranked on directly.
- **Scenery type** (primary user filter): controlled vocabulary, many-to-many.
  Draft buckets: street, architecture, nature/parks, waterfront, temples/shrines,
  neon/nightlife, food. Raw Flickr tags mapped → buckets in the pipeline.
- **Time-of-day suitability** (derived): from timestamp distribution of
  high-engagement Flickr photos at each location. Bucket labels: golden hour,
  blue hour, night, daytime. Actual clock times computed per location+date via
  sun-position library (astral), not hardcoded.

### Contextual (dynamic, per location + time)
- **Crowd level** (user filter): Google Places popular times.
- **Weather / conditions** (re-ranking, not a filter): weather API + is_outdoor flag.
  Lets results re-rank live (e.g. rain → covered spots first).

## Data model
Four tables (see also db/schema.sql):
- **locations** — intrinsic core. One row per spot: id, city, name, lat, lng,
  photogenicity, flickr_photo_count, flickr_engagement, google_rating, is_outdoor.
- **location_tags** — many-to-many scenery tags: (location_id, scenery_tag).
- **location_timeslots** — derived time suitability: (location_id, time_bucket, suitability).
- **conditions** — contextual snapshots: (location_id, captured_at, crowd_level, weather).
  v1 may skip storing this and call the weather API live at query time.

### Recommendation query shape
JOIN locations → location_tags (filter to chosen scenery) → location_timeslots
(filter to chosen time) → optionally check conditions →
ORDER BY weighted blend of photogenicity × tag-match-count × suitability.

## Tech decisions
- **Database:** SQLite first (zero setup, single file, stdlib). Keep SQL standard
  so it ports to Postgres later; note portability in README. Do not build the
  Postgres decision into the repo yet.
- **Stack:** Python-native throughout (Pandas, GeoPandas, requests, astral,
  Streamlit, Plotly) — consistent with Project A and with US tech recruiting.
- **Secrets:** API keys via .env (git-ignored), .env.example committed as template.

## Resolved decisions

### Scenery vocabulary (locked)
Seven buckets, stored as underscore tokens (enforced by CHECK in db/schema.sql):
street, architecture, nature_parks, waterfront, temples_shrines, neon_nightlife, food.
Disambiguation: neon_nightlife = illuminated night scenes; street = daytime urban.
A location may hold several (many-to-many via location_tags).

Tag mapping — Place type is primary where strong, Flickr tags fill the rest:
- temples_shrines ← Place type place_of_worship  | tags: temple, shrine, torii, jinja, pagoda
- nature_parks    ← Place type park              | tags: park, garden, sakura, momiji, pond
- food            ← restaurant/cafe/market       | tags: food, ramen, sushi, izakaya, market
- neon_nightlife  ← bar/night_club               | tags: neon, night, illumination, kabukicho
- waterfront      ← (Flickr-led)                 | tags: river, bay, bridge, canal, sumida
- architecture    ← (Flickr-led)                 | tags: architecture, building, tower, facade
- street          ← (Flickr-led)                 | tags: street, alley, crossing, backstreet
Note: Tokyo Flickr tags include Japanese romaji (sakura, torii, jinja) — mapping must include these.
Top four buckets are Place-type-anchored (high precision); bottom three lean on noisier Flickr tags.

### Photogenicity formula (locked)
Within each city, per location (min 5 photos, else score = NULL):
- density_n    = normalized log(1 + flickr_photo_count)
- engagement_n = normalized median(favorites per photo)
- rating_n     = normalized (google_rating / 5)
- photogenicity = 0.30·density_n + 0.45·engagement_n + 0.25·rating_n

Rationale: engagement weighted highest (quality signal, avoids rebuilding a crowd map);
favorites not views (views are inflated), median not mean (resists one viral photo);
density necessary but minority; Google rating lowest (measures "good to visit," not
"good to shoot") but kept as an independent cross-check. Normalized within city so
Tokyo's volume doesn't swamp smaller cities.