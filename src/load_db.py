"""Load scored parquet tables into the SQLite database defined in db/schema.sql."""

import sqlite3
import pandas as pd
from pathlib import Path

INTERIM_DIR = Path("data/interim")
DB_PATH = Path("db/hotspots.db")
SCHEMA_PATH = Path("db/schema.sql")


def load_city(city):
    scored = pd.read_parquet(INTERIM_DIR / f"{city}_scored.parquet")
    tags = pd.read_parquet(INTERIM_DIR / f"{city}_location_tags.parquet")
    slots = pd.read_parquet(INTERIM_DIR / f"{city}_timeslots.parquet")

    # Fresh database from schema
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text())

    # --- locations ---
    loc_rows = pd.DataFrame({
        "location_id": scored["cluster"].astype(int),
        "source_place_id": scored["place_id"],
        "city": scored["city"] if "city" in scored else city,
        "name": scored["name"].fillna("(unnamed spot)"),
        "lat": scored["lat"],
        "lng": scored["lng"],
        "is_outdoor": 1,  # refine later; default outdoor
        "flickr_photo_count": scored["n_photos"].astype(int),
        "flickr_engagement": scored["engagement_raw"],
        "google_rating": scored["google_rating"],
        "photogenicity": scored["photogenicity"],
    })
    loc_rows.to_sql("locations", conn, if_exists="append", index=False)

    # --- location_tags ---
    tag_rows = tags.rename(columns={"cluster": "location_id"})[["location_id", "scenery_tag"]].copy()
    tag_rows["location_id"] = tag_rows["location_id"].astype(int)
    tag_rows = tag_rows[tag_rows.location_id.isin(loc_rows.location_id)]
    tag_rows.to_sql("location_tags", conn, if_exists="append", index=False)

    # --- location_timeslots ---
    slot_rows = slots.rename(columns={"cluster": "location_id"})[["location_id", "time_bucket", "suitability"]].copy()
    slot_rows["location_id"] = slot_rows["location_id"].astype(int)
    slot_rows = slot_rows[slot_rows.location_id.isin(loc_rows.location_id)]
    slot_rows.to_sql("location_timeslots", conn, if_exists="append", index=False)

    conn.commit()

    # Verify
    for tbl in ["locations", "location_tags", "location_timeslots"]:
        n = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"{tbl:22} {n:,} rows")
    conn.close()
    print(f"\nWrote {DB_PATH}")


if __name__ == "__main__":
    load_city("tokyo")