# Findings

Running log of decisions, data quirks, and things learned while building.

## Ingest & data acquisition

- Flickr disabled API key creation for free accounts (2026); requires a Pro subscription.
  Mitigated by decoupling ingest from scoring — raw responses cached to data/raw/ so
  scoring can be re-run indefinitely without API access.
- Flickr caps pagination at ~4,000 results per query regardless of the reported total
  → ingest must tile the city into a grid of small bboxes.
- sort=interestingness-desc means the photos we can actually reach are the most-engaged
  ones, which aligns with the scoring formula (engagement weighted 45%). The pagination
  cap costs less than it would under any other sort order.
- Tokyo Flickr density is very high (~100k geotagged photos in a single central bbox).
  Validates Tokyo as the launch city — no shortage of data.
- Photo density is highly non-uniform and bimodal, not gradual: dense wards saturate the
  per-tile cap (5,000); water tiles collapse to near-zero.
- Tokyo bbox (139.60-139.92 E) includes substantial Tokyo Bay water in the eastern
  columns — tiles c08/c09 return ~4-8 photos (open water). Tightening the eastern bound
  to ~139.87 would eliminate ~15-20 wasted API calls on a re-run.
- Uniform 10x10 grid: many tiles saturate at the cap, meaning available photos exceed
  what one query can reach. → Candidate improvement: adaptive tiling (subdivide only
  saturated tiles).
- fetch_bbox returns photos fetched *this run*, not total cached — so resumed runs report
  misleading zeros for already-complete tiles. Cosmetic, but the progress output should
  distinguish "skipped (cached)" from "fetched 0".

## Parsing & deduplication

- 20% of parsed rows were duplicates (67,956 of 331,579), largely from re-running the
  ingest after a mid-run timeout. Deduplicating on photo id is essential — without it,
  popular photos double-count and inflate engagement scores on exactly the dense
  locations the formula weights most.
- Flickr tags are heavily polluted with camera/lens gear (e.g. "distagon", "fe35mmf14").
  Scenery mapping must filter gear terms; reinforces anchoring buckets on Google types.

## Clustering (photos → locations)

- DBSCAN eps=100m chained across Tokyo's continuous density — top cluster spanned 3,771m
  (a district, not a spot). eps=50m fixed it: max extent ~1,028m, median 216m. Cost:
  noise rose 14.9% → 29.6%, acceptable (long tail of one-off snapshots).
- Raw photo count is a broken density signal. Clusters with 700-1,000 photos from a
  SINGLE owner exist (someone's home/workplace). Enthusiast niches (plane spotters near
  Haneda) show 30-45 photos/owner. Genuine hotspots show 2-4 photos/owner across hundreds
  of owners. → density must use unique_owners, not photo count.
- photo_clusters.parquet retains all DBSCAN clusters; only the owner-filtered subset
  become locations. Per-cluster aggregations must filter to valid location clusters or
  they compute phantom rows (caught this in timeofday).
- Cluster fragmentation: eps=50m split some large venues (Budokan, Rainbow Bridge) into
  adjacent clusters that both matched one Google place_id (107-234m apart). Merged
  fragments by remapping photos to a canonical cluster and pooling evidence, rather than
  dropping the smaller (which would discard real photographers' signal).

## Scoring formula

- Favorites are zero-inflated: 57% of individual photos have 0 faves. Per-location
  median faves == 0 for 56.4% of locations, making the median useless as a discriminator
  despite being the theoretically "correct" robust statistic for skewed data.
  → Replaced median(faves) with mean(log(1+faves)): only 21.6% zeros, clean spread.
  Retains outlier-resistance via the log rather than via the median.
- 4 locations had all-zero-favorite photos → engagement weights summed to 0 →
  suitability = weight/0 = NaN. The schema's NOT NULL constraint caught this at load
  time. Fixed at source: fall back to equal (count-based) weighting when a cluster's
  total engagement is zero.
- Raw time-of-day suitability favors daytime (65% baseline vs golden hour 7%).
  Normalized time_fit against the citywide baseline so golden/blue-hour specialists
  surface correctly — Tennōji/Tsukiji Hongwan-ji now lead temple+golden-hour instead of
  being buried under famous all-day spots.

## Places enrichment & scenery tagging

- Places API (New) Nearby Search, rankPreference=POPULARITY, radius=150m matches cluster
  centroids to sensible POIs (top: Metro Gov Building, Omoide Yokocho, Nakamise, Shibuya
  Crossing). Match distances 39-140m — centroids land close to real POIs; radius well-tuned.
- ~40% of enriched locations carry a transit type (stations). Flickr geotags cluster at
  arrival points, but stations are rarely the photo subject. Station type should DEFER to
  Flickr tags, not mark a location non-photogenic.
- Google types anchor park/temple/food/museum buckets cleanly (~half the locations);
  station-typed and generic 'tourist_attraction' locations (~the other half) are bucketed
  from Flickr tags instead. Locations with no signal from either → tagged 'general',
  excluded from scenery filters.
- Found type→bucket map gaps by spot-checking unbucketed locations against known photo
  spots: observation decks, art museums, tea houses, Budokan were being dropped.
  Validating output against ground truth caught what aggregate stats hid.
- Google-type precedence suppresses Flickr 'temple' tags on clearly non-worship spots
  (stations, malls, zoo, event venues): temple-tagged 49 → 40, obvious false positives
  removed. Two ambiguous stragglers (Omoide Yokocho, Metro Gov Building) left in rather
  than broadening the suppression list and risking false negatives on real temples.
- Extended station-type suppression to street/architecture buckets: street 61→36,
  architecture 193→165. Removed commuter stations from street results (were ~half the
  top list). Residual bleed remains on non-station commercial venues (malls, zoo) and
  photogenic temples that street photographers shoot around — accepted as a known limit
  rather than adding per-type rules with diminishing returns.