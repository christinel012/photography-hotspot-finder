# Findings

Running log of decisions, data quirks, and things learned while building.

## Data notes

- Tokyo Flickr density is very high (~100k geotagged photos in a single central bbox).
  Validates Tokyo as the launch city — no shortage of data.
- Photo density is highly non-uniform: dense wards saturate the per-tile cap (5,000),
  outer tiles drain naturally (~600).
- Flickr tags are heavily polluted with camera/lens gear (e.g. "distagon", "fe35mmf14").
  Scenery mapping must filter gear terms; reinforces anchoring buckets on Google Place types.

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