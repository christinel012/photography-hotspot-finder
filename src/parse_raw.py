"""Parse cached Flickr JSON responses into a flat photo-level table.

Reads data/raw/<city>/*.json, extracts the fields needed for scoring,
and writes a single Parquet file to data/interim/.
"""

import json
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw")
INTERIM_DIR = Path("data/interim")

# Fields we requested via `extras` in the API call.
FIELDS = ["id", "title", "latitude", "longitude", "tags", "datetaken", "views", "count_faves", "owner"]


def parse_city(city):
    """Parse all cached JSON pages for a city into one DataFrame."""
    city_dir = RAW_DIR / city
    files = sorted(city_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No cached JSON in {city_dir}. Run the ingest first.")

    rows = []
    for path in files:
        with open(path) as f:
            data = json.load(f)

        tile_id = path.stem.split("_")[0]

        for photo in data["photos"]["photo"]:
            row = {field: photo.get(field) for field in FIELDS}
            row["tile_id"] = tile_id
            rows.append(row)

    df = pd.DataFrame(rows)
    print(f"Parsed {len(files)} files -> {len(df):,} photo rows")

    # Types: the API returns everything as strings.
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["views"] = pd.to_numeric(df["views"], errors="coerce")
    df["count_faves"] = pd.to_numeric(df["count_faves"], errors="coerce")
    df["datetaken"] = pd.to_datetime(df["datetaken"], errors="coerce")

    before = len(df)
    df = df.drop_duplicates(subset="id")
    print(f"Dropped {before - len(df):,} duplicate photos (overlapping tiles / repeat pages)")

    df = df.dropna(subset=["latitude", "longitude"])
    df["city"] = city

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    out_path = INTERIM_DIR / f"{city}_photos.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(df):,} rows to {out_path}")

    return df


if __name__ == "__main__":
    parse_city("tokyo")