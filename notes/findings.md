# Findings

Running log of decisions, data quirks, and things learned while building.

## Data notes

## Scoring notes

- Tokyo Flickr density is very high (~100k geotagged photos in a single central bbox).
- Flickr caps pagination at ~4,000 results per query regardless of reported total
  → ingest must tile the city into a grid of small bboxes.
- sort=interestingness-desc means the reachable 4k are the most-engaged photos,
  which aligns with the scoring formula (engagement weighted 45%).
- Flickr tags are heavily polluted with camera/lens gear (e.g. "distagon", "fe35mmf14").
  Scenery mapping must filter gear terms; reinforces anchoring buckets on Google Place types.
  
## Gotchas
