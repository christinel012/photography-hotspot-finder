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

### Photogenicity formula (locked, revised after EDA)

Within each city, per location (min 5 photos, else score = NULL):
- density_n     = normalized log(1 + unique_owners)
- engagement_n  = normalized owner-averaged weighted mean of log(1 + favorites),
                  where each photo's weight = 0.5 ** (age_in_years / 5)
- rating_n      = normalized (google_rating / 5)
- photogenicity = 0.30·density_n + 0.45·engagement_n + 0.25·rating_n

Rationale (unchanged): engagement weighted highest — it's the quality signal that
stops the score from rebuilding a tourist-crowd map. Favorites not views (views are
inflated by search traffic). Density necessary but minority. Google rating lowest —
it measures "good to visit," not "good to shoot" — but kept as an independent
cross-check Flickr dynamics can't game. Normalized within city so Tokyo's volume
doesn't swamp smaller cities.

REVISION 1 — median → mean of log(1+faves).
Originally specified median(favorites per photo) as the outlier-resistant choice.
EDA showed favorites are zero-inflated: 57% of individual photos have 0 faves, and
the per-location median is 0 for 56.4% of locations. The median — the textbook robust
statistic for skewed data — is useless on zero-inflated data: the highest-weighted
term in the formula would have been a near-constant across most of the dataset.
Replaced with mean of log(1+faves): 21.6% zeros, clean spread (quartiles 0.05 / 0.43
/ 1.39). Outlier-resistance is now provided by the log transform rather than by the
median — a single 5,000-fave photo contributes ~8.5, not 5,000.

REVISION 2 — recency weighting on engagement.
Photo dates span 2004–2026, peaking 2013–2017 (Flickr's own peak era), with ~46k
photos from 2023+. Unweighted scoring would reflect a Tokyo that has partly changed.
Applied exponential decay with a 5-year half-life to the engagement term only.

Deliberately NOT applied to density: density measures "do people photograph here,"
and a 2013 photo is genuine evidence of that — downweighting it would distort a count
into something that isn't a count. Engagement measures "are photos here good," where
recency legitimately matters.

Weighted MEAN (divide by Σw), not weighted sum — so a location with many old photos
doesn't out-score one with fewer recent ones. Preserves the quality-not-volume thesis.

Open question: the min-5-photos floor is now less meaningful, since 5 photos from 2012
carry ~0.5 effective weight. A weighted minimum (Σw >= 3) may be better. Shipping the
simple version first.

REVISION 3 — photo_count → unique_owners in the density term.
Clustering (DBSCAN, eps=50m, min_samples=20) surfaced clusters ranked by raw photo
count that were not photogenic places at all:
  - cluster 29:   1,005 photos, 1 owner
  - cluster 1360:   955 photos, 1 owner
  - cluster 1214:   752 photos, 1 owner
  - clusters near Haneda / Tokyo Bay: 30-45 photos per owner (plane spotters)
A single prolific uploader — or a small enthusiast group shooting one subject
repeatedly — could rank above genuine hotspots. Raw photo count measures enthusiast
obsession, not photogenicity.

By contrast, clusters ranked by UNIQUE OWNERS surface recognizable Tokyo: Shinjuku,
Ginza, Asakusa/Senso-ji, Roppongi — each with 400-900 distinct photographers at
2-4 photos per owner. Many independent people choosing to photograph the same place
IS the photogenicity signal.

→ density = log(1 + unique_owners).

Engagement is aggregated per-owner as well (average each owner's photos, then average
across owners), so one photographer with 1,000 uploads cannot dominate a location's
engagement score. One photographer, one vote.

Post-clustering filter: require >= 10 distinct owners for a cluster to become a
location. min_samples in DBSCAN counts photos, so a 20-photo/1-owner cluster would
otherwise survive.

### Timestamp validity
Flickr EXIF dates include junk (observed range 1870–2042). Timestamps outside
2004–2026 are nulled (not dropped — the photo's coordinates, tags, and favorites
remain valid for density and engagement; only time-of-day derivation excludes it).
Affects 469 rows (0.18%).