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

## Open decisions (TODO)
- [ ] Finalize scenery vocabulary (lock the exact bucket list + the raw-tag → bucket mapping).
- [ ] Finalize photogenicity weighting formula (relative weights of density,
      engagement, rating; normalization approach — likely within-city like Project A).