# Findings

Running log of decisions, data quirks, and things learned while building.

## Data notes

- Tokyo Flickr density is very high (~100k geotagged photos in a single central bbox).
  Validates Tokyo as the launch city — no shortage of data.
- Photo density is highly non-uniform: dense wards saturate the per-tile cap (5,000),
  outer tiles drain naturally (~600).
- Flickr tags are heavily polluted with camera/lens gear (e.g. "distagon", "fe35mmf14").
  Scenery mapping must filter gear terms; reinforces anchoring buckets on Google Place types.
- Tokyo bbox (139.60-139.92 E) includes substantial Tokyo Bay water in the eastern
  columns — tiles c08/c09 return ~4-8 photos (open water). Tightening the eastern
  bound to ~139.87 would eliminate ~15-20 wasted API calls on a re-run.
- Saturation is geographically structured: land tiles in the dense band all hit the
  5,000 cap; water tiles collapse to near-zero. Density is bimodal, not gradual.
- fetch_bbox returns photos fetched *this run*, not total cached — so resumed runs
  report misleading zeros for already-complete tiles. Cosmetic, but the progress
  output should distinguish "skipped (cached)" from "fetched 0".
- 20% of parsed rows were duplicates (67,956 of 331,579), largely from re-running the
  ingest after a mid-run timeout. Deduplicating on photo id is essential — without it,
  popular photos double-count and inflate engagement scores on exactly the dense
  locations the formula weights most.
- Favorites are zero-inflated: 57% of individual photos have 0 faves.
  Per-location (200m grid proxy): median faves == 0 for 56.4% of locations,
  making the median useless as a discriminator despite being the theoretically
  "correct" robust statistic for skewed data.
  → Replaced median(faves) with mean(log(1+faves)): only 21.6% zeros, clean spread
  (quartiles 0.05 / 0.43 / 1.39). Retains outlier-resistance via the log rather than
  via the median. Weights unchanged.
- DBSCAN eps=100m chained across Tokyo's continuous density — top cluster spanned
  3,771m (a district, not a spot). eps=50m fixed it: max extent ~1,028m, median 216m.
  Cost: noise rose 14.9% -> 29.6%, which is acceptable (long tail of one-off snapshots).
- Raw photo count is a broken density signal. Clusters with 700-1,000 photos from a
  SINGLE owner exist (someone's home/workplace). Enthusiast niches (plane spotters
  near Haneda) show 30-45 photos/owner. Genuine hotspots show 2-4 photos/owner across
  hundreds of owners. → density must use unique_owners, not photo count.

## Scoring notes

- sort=interestingness-desc means the photos we can actually reach are the most-engaged
  ones, which aligns with the scoring formula (engagement weighted 45%). The pagination
  cap costs less than it would under any other sort order.

## Gotchas

- Flickr disabled API key creation for free accounts (2026); requires a Pro subscription.
  Mitigated by decoupling ingest from scoring — raw responses cached to data/raw/ so
  scoring can be re-run indefinitely without API access.
- Flickr caps pagination at ~4,000 results per query regardless of the reported total
  → ingest must tile the city into a grid of small bboxes.
- Uniform 10x10 grid: many tiles saturate at the cap, meaning available photos exceed
  what one query can reach.
  → Candidate improvement: adaptive tiling (subdivide only saturated tiles).
- Places API (New) Nearby Search with rankPreference=POPULARITY, radius=150m matches
  cluster centroids to sensible POIs: top clusters -> Tokyo Metro Gov Building, Omoide
  Yokocho, Nakamise, Shibuya Crossing, Ginza Station. Match distances 39-140m (centroids
  land close to real POIs; 150m radius well-tuned).
- Google 'types' skews to generic 'tourist_attraction' for famous spots — confirms types
  alone can't fill scenery buckets; hybrid with Flickr tags needed. Some clusters match
  stations/konbini (photogenic-adjacent, not photo spots) — retain types to flag later.



- ~40% of enriched locations carry a transit type (transit_station 171, train_station
  96, transportation_service 191, subway_station 21). Flickr geotags cluster at stations
  (arrival points), but stations are rarely the photo subject. Google types can't tell a
  photogenic historic station from a plain platform.
  → Scenery tagging: Google types anchor park/temple/food/museum buckets cleanly (~half
  the locations); station-typed and generic 'tourist_attraction' locations (~the other
  half) must be bucketed from Flickr tags instead.
  → Station type should DEFER to Flickr tags, not mark a location non-photogenic.

- Scenery tagging: 296/502 locations get a scenery bucket; 206 are transit/commercial
  (stations, malls, hotels) with no scenery signal from Google types OR owner-gated
  Flickr tags -> tagged 'general', excluded from scenery filters.
- Found type->bucket map gaps by spot-checking unbucketed locations against known Tokyo
  photo spots: observation decks, art museums, tea houses, Budokan were being dropped.
  Validating the pipeline output against ground truth caught what the aggregate stats hid.