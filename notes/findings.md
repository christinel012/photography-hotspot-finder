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
