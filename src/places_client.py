"""Google Places API (New) client — enrich cluster centroids with POI data.

Uses Nearby Search to find the most prominent place near each cluster centroid,
recording match distance so weak matches can be treated as 'discovered' spots.
"""

import os
import time
import json
import math
from pathlib import Path

import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
if not API_KEY:
    raise RuntimeError("GOOGLE_PLACES_API_KEY not found in .env")

NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
INTERIM_DIR = Path("data/interim")
RAW_DIR = Path("data/raw")

FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.rating",
    "places.userRatingCount",
    "places.types",
    "places.location",
])

SEARCH_RADIUS_M = 150
REQUEST_DELAY_SEC = 0.1


def haversine_m(lat1, lng1, lat2, lng2):
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def nearby_search(lat, lng, radius=SEARCH_RADIUS_M):
    """Return the most prominent place near (lat, lng), or None."""
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    body = {
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(radius),
            }
        },
        "rankPreference": "POPULARITY",
        "maxResultCount": 1,
    }
    resp = requests.post(NEARBY_URL, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    places = data.get("places", [])
    return places[0] if places else None


def enrich_locations(city, radius=SEARCH_RADIUS_M, overwrite=False):
    """Match every cluster centroid to a nearby POI. Resumable via raw cache."""
    locs = pd.read_parquet(INTERIM_DIR / f"{city}_locations.parquet")
    cache_dir = RAW_DIR / f"{city}_places"
    cache_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for i, r in enumerate(locs.itertuples(), start=1):
        cache_path = cache_dir / f"cluster_{r.cluster}.json"

        if cache_path.exists() and not overwrite:
            place = json.loads(cache_path.read_text())
        else:
            place = nearby_search(r.lat, r.lng, radius=radius)
            cache_path.write_text(json.dumps(place))
            time.sleep(REQUEST_DELAY_SEC)

        if place:
            loc = place["location"]
            dist = haversine_m(r.lat, r.lng, loc["latitude"], loc["longitude"])
            rows.append({
                "cluster": r.cluster,
                "place_id": place["id"],
                "name": place["displayName"]["text"],
                "google_rating": place.get("rating"),
                "user_rating_count": place.get("userRatingCount"),
                "types": place.get("types", []),
                "match_dist_m": round(dist, 1),
            })
        else:
            rows.append({
                "cluster": r.cluster,
                "place_id": None, "name": None, "google_rating": None,
                "user_rating_count": None, "types": [], "match_dist_m": None,
            })

        if i % 50 == 0:
            print(f"[{i}/{len(locs)}] enriched")

    enriched = pd.DataFrame(rows)

    # Merge back onto the locations table
    out = locs.merge(enriched, on="cluster", how="left")
    matched = out.place_id.notna().sum()
    print(f"\nMatched {matched}/{len(out)} clusters to a place")
    print(f"No match: {len(out) - matched}")

    out.to_parquet(INTERIM_DIR / f"{city}_locations_enriched.parquet", index=False)
    print(f"Wrote {city}_locations_enriched.parquet")
    return out