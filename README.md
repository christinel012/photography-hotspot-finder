# Shoot Here — a photography hotspot finder

**A recommendation engine that tells photographers where to shoot in a city, ranked by what people *actually* photograph — not just what's popular.** You pick what you want to shoot (street, temples, waterfront…) and when (golden hour, blue hour, night…), and it returns ranked spots on a map. Built city-agnostic; launched with Tokyo.

🔗 **Live app:** https://shoot-here.streamlit.app/ (Streamlit Community Cloud)_
📓 **Full design log:** [`docs/design.md`](docs/design.md) · [`notes/findings.md`](notes/findings.md)

---

## What it does

Most "best photo spots" lists are popularity rankings — they surface whatever is famous. This tool asks a different question: *where do lots of different photographers independently choose to shoot, and where do the photos they take actually get loved?* It then lets you filter that by the kind of photography you want and the time of day, and ranks the results.

The core idea is a **photogenicity score** per location, combined with a **time-of-day fit** that measures whether a spot is *especially* good at, say, golden hour — relative to how rare golden-hour photography is city-wide.

## How it was built

A five-stage pipeline, each stage cached so the whole thing is reproducible and the paid APIs are only needed once:

1. **Ingest** — 264k geotagged photos pulled from the Flickr API across a tiled grid of Tokyo (Flickr caps pagination at ~4k results per query, so the city is covered tile by tile).
2. **Cluster** — DBSCAN (haversine metric) groups photos into candidate locations; an owner-diversity filter removes single-photographer clusters.
3. **Enrich** — each cluster is matched to a Google Places POI for its name, rating, and place types.
4. **Score & tag** — the photogenicity formula runs; locations are tagged into seven scenery buckets from a hybrid of Google place types and Flickr tags; time-of-day suitability is derived from the sun's elevation at each photo's capture time.
5. **Serve** — everything loads into a SQLite database; the Streamlit app runs live SQL queries against it.

## The photogenicity model

```
photogenicity = 0.30·density + 0.45·engagement + 0.25·rating   (normalized within city)
```

- **density** = `log(1 + unique_owners)` — how many *distinct* photographers, not photo volume
- **engagement** = owner-averaged, recency-weighted mean of `log(1 + favorites)` — the quality signal, weighted highest
- **rating** = Google rating / 5 — an independent cross-check

The interesting part isn't the formula — it's the **three times the data proved the first version wrong**:

1. **Median → log-mean.** The engagement term first used the median favorites (the textbook robust statistic). But favorites are zero-inflated — 57% of photos have zero, and the per-location median was 0 for 56% of locations, making the highest-weighted term a near-constant. Switched to the mean of `log(1+favorites)`.
2. **Photo count → unique owners.** Ranking by raw photo count surfaced a location with 1,000 photos from a *single* owner (someone's home) and plane-spotter fences near Haneda. Density now counts distinct photographers.
3. **Raw → baseline-normalized time fit.** Two-thirds of all photos are taken in daylight, so raw time shares always favor daytime. Time-of-day fit is normalized against the city-wide baseline, so genuine golden-hour specialists surface instead of famous all-day landmarks.

Full reasoning and the evidence behind each revision is in [`docs/design.md`](docs/design.md).

## Tech stack

**Python** · **SQL / SQLite** · pandas · GeoPandas · scikit-learn (DBSCAN) · astral (solar position) · Streamlit · Plotly
**APIs:** Flickr, Google Places (New)

The database is SQLite for zero-config portability; the schema is written in standard SQL and designed to port to Postgres.

## Project structure

```
src/
  flickr_client.py   # tiled, rate-limited, resumable photo ingest
  parse_raw.py       # raw JSON -> deduplicated photo table
  cluster.py         # DBSCAN clustering + owner-diversity filter
  places_client.py   # Google Places enrichment
  scenery.py         # scenery bucket tagging (Google types + Flickr tags)
  timeofday.py       # time-of-day suitability via solar elevation
  scoring.py         # the photogenicity formula
  dedup.py           # merge fragmented duplicate clusters
  load_db.py         # load scored data into SQLite
db/
  schema.sql         # four-table schema (locations, tags, timeslots, conditions)
app/
  app.py             # the Streamlit recommendation app
docs/design.md       # locked design decisions + reasoning
notes/findings.md    # data quirks and lessons, logged as they emerged
```

## Running it locally

```bash
python -m venv hotspot-env && source hotspot-env/bin/activate
pip install -r requirements.txt
streamlit run app/app.py
```

The app reads the committed SQLite database, so it runs without any API keys. Regenerating the data from scratch (the `src/` pipeline) requires Flickr and Google Places API keys — copy `.env.example` to `.env` and add your own.

## Notes on data & licensing

Code is MIT-licensed. The photo *metadata* is accessed via the Flickr and Google Places APIs and remains subject to their terms — this project stores and analyzes metadata (coordinates, tags, engagement counts) only; it does not host or redistribute any photos. "See photos" links point back to Flickr and Google Maps rather than embedding images.

---

*Built by Christine Li as a solo portfolio project. [GitHub](https://github.com/christinel012) · [LinkedIn](https://www.linkedin.com/in/christineli012)*