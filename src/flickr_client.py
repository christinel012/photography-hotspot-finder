"""Flickr API client.

Fetches geotagged photos for a city: tags, engagement (views/favorites),
and timestamps. Feeds photogenicity scoring and time-of-day suitability.
"""

## Config and key loading
import os
import time
import json
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("FLICKR_API_KEY")
if not API_KEY:
    raise RuntimeError("FLICKR_API_KEY not found. Copy .env.example to .env and add your key.")

API_URL = "https://api.flickr.com/services/rest/"
RAW_DIR = Path("data/raw")

# Flickr allows 3600 queries/hour = 1/sec. Stay well under.
REQUEST_DELAY_SEC = 0.5
PER_PAGE = 250          # Flickr max is 500; 250 keeps responses manageable
MAX_PAGES = 20          # safety cap per bbox tile
MAX_RETRIES = 4
BACKOFF_BASE_SEC = 2

## The search function
def search_photos(bbox, page=1, min_upload_date=None):
    """Query flickr.photos.search for geotagged photos in a bounding box."""
    params = {
        "method": "flickr.photos.search",
        "api_key": API_KEY,
        "bbox": bbox,
        "has_geo": 1,
        "extras": "geo,tags,date_taken,views,count_faves,owner_name",
        "per_page": PER_PAGE,
        "page": page,
        "sort": "interestingness-desc",
        "format": "json",
        "nojsoncallback": 1,
    }
    if min_upload_date:
        params["min_upload_date"] = min_upload_date

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(API_URL, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()
            break
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as e:
            last_error = e
            wait = BACKOFF_BASE_SEC * (2 ** attempt)
            print(f"  request failed ({type(e).__name__}), retrying in {wait}s...")
            time.sleep(wait)
    else:
        raise RuntimeError(f"Flickr request failed after {MAX_RETRIES} attempts") from last_error

    if data.get("stat") != "ok":
        raise RuntimeError(f"Flickr API error: {data.get('message')}")

    return data

## Paginated fetch with caching
def fetch_bbox(bbox, tile_id, city, max_pages=MAX_PAGES, overwrite=False):
    """Page through one bbox, caching each raw response to data/raw/.

    Returns the number of photos fetched. Skips tiles already cached
    unless overwrite=True, so an interrupted run can be resumed.
    """
    out_dir = RAW_DIR / city
    out_dir.mkdir(parents=True, exist_ok=True)

    total_fetched = 0

    for page in range(1, max_pages + 1):
        cache_path = out_dir / f"{tile_id}_p{page:03d}.json"

        if cache_path.exists() and not overwrite:
            continue

        data = search_photos(bbox, page=page)
        photos = data["photos"]["photo"]

        if not photos:
            break

        with open(cache_path, "w") as f:
            json.dump(data, f)

        total_fetched += len(photos)

        if page >= int(data["photos"]["pages"]):
            break

        time.sleep(REQUEST_DELAY_SEC)

    return total_fetched

## Tiling and the full city ingest
CITIES = {
    "tokyo": {
        # 23 special wards — excludes Tokyo's Pacific islands.
        "bbox": (139.60, 35.53, 139.92, 35.82),
        "grid": 10,
    },
}


def make_tiles(bbox, grid):
    """Split a bounding box into grid x grid smaller bboxes.

    Yields (tile_id, "min_lng,min_lat,max_lng,max_lat") pairs.
    """
    min_lng, min_lat, max_lng, max_lat = bbox
    lng_step = (max_lng - min_lng) / grid
    lat_step = (max_lat - min_lat) / grid

    for row in range(grid):
        for col in range(grid):
            t_min_lng = min_lng + col * lng_step
            t_max_lng = t_min_lng + lng_step
            t_min_lat = min_lat + row * lat_step
            t_max_lat = t_min_lat + lat_step

            tile_id = f"r{row:02d}c{col:02d}"
            tile_bbox = f"{t_min_lng:.4f},{t_min_lat:.4f},{t_max_lng:.4f},{t_max_lat:.4f}"
            yield tile_id, tile_bbox


def ingest_city(city):
    """Fetch all tiles for a city. Resumable — skips already-cached tiles."""
    if city not in CITIES:
        raise ValueError(f"Unknown city '{city}'. Known: {list(CITIES)}")

    config = CITIES[city]
    tiles = list(make_tiles(config["bbox"], config["grid"]))
    grand_total = 0

    for i, (tile_id, tile_bbox) in enumerate(tiles, start=1):
        count = fetch_bbox(tile_bbox, tile_id=tile_id, city=city)
        grand_total += count
        print(f"[{i}/{len(tiles)}] {tile_id}  {count:>5} photos  (running: {grand_total})")

    print(f"\nDone. {grand_total} photos cached to {RAW_DIR / city}")
    return grand_total