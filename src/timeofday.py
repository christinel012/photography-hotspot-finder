"""Derive time-of-day suitability per location from photo timestamps.

For each photo, compute the sun's elevation at its capture time and Tokyo's
location, classify into golden/blue/night/daytime, then aggregate an
engagement-weighted vote per location. Golden hour is computed astronomically
(solar elevation per date), not hardcoded to a clock time.
"""

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import timezone, timedelta

from astral.sun import elevation
from astral import Observer

INTERIM_DIR = Path("data/interim")

# Tokyo. datetaken is naive local camera time; we treat it as JST.
TOKYO = Observer(latitude=35.68, longitude=139.76)
JST = timezone(timedelta(hours=9))

VALID_YEAR_MIN = 2004
VALID_YEAR_MAX = 2026

TIME_BUCKETS = ["golden_hour", "blue_hour", "daytime", "night"]


def classify_elevation(elev_deg):
    """Sun elevation (degrees) -> time-of-day bucket."""
    if elev_deg >= 6:
        return "daytime"
    elif elev_deg >= -4:
        return "golden_hour"
    elif elev_deg >= -6:
        return "blue_hour"
    else:
        return "night"


def derive_timeslots(city):
    pc = pd.read_parquet(INTERIM_DIR / f"{city}_photo_clusters.parquet")

    # Keep only clusters that survived the owner-diversity filter (i.e. are locations)
    locs = pd.read_parquet(INTERIM_DIR / f"{city}_locations.parquet")
    valid_clusters = set(locs.cluster)
    before_c = pc.cluster.nunique()
    pc = pc[pc.cluster.isin(valid_clusters)]
    print(f"Filtered to {pc.cluster.nunique()} location clusters (from {before_c} raw clusters)")

    # Valid timestamps only (junk EXIF: 1870, 2042, etc.)
    pc = pc.dropna(subset=["datetaken"]).copy()
    yr = pc["datetaken"].dt.year
    before = len(pc)
    pc = pc[(yr >= VALID_YEAR_MIN) & (yr <= VALID_YEAR_MAX)]
    print(f"Dropped {before - len(pc):,} photos with invalid timestamps")

    # Engagement weight per photo (same signal as photogenicity)
    pc["weight"] = np.log1p(pc["count_faves"].fillna(0))

    # Sun elevation per photo. Cache by (date, hour, minute) to avoid recomputing
    # the same instant hundreds of times.
    print("Computing solar elevation per photo (this takes a moment)...")
    dt_jst = pc["datetaken"].dt.tz_localize(JST)

    def elev_for(ts):
        return elevation(TOKYO, ts.to_pydatetime())

    # Round to the minute and cache — massively fewer unique calls than 260k.
    key = dt_jst.dt.floor("min")
    unique = pd.Series(key.unique())
    elev_map = {t: elevation(TOKYO, pd.Timestamp(t).to_pydatetime()) for t in unique}
    pc["elev"] = key.map(elev_map)
    pc["bucket"] = pc["elev"].apply(classify_elevation)

    # Engagement-weighted vote per (cluster, bucket)
    votes = pc.groupby(["cluster", "bucket"])["weight"].sum().reset_index()
    totals = votes.groupby("cluster")["weight"].sum().rename("total")
    votes = votes.join(totals, on="cluster")
    votes["suitability"] = votes["weight"] / votes["total"]

    out = votes[["cluster", "bucket", "suitability"]].rename(columns={"bucket": "time_bucket"})
    out.to_parquet(INTERIM_DIR / f"{city}_timeslots.parquet", index=False)

    print(f"\nTimeslot rows: {len(out)}")
    print("\nbucket distribution (share of all votes):")
    print(pc.groupby("bucket")["weight"].sum().div(pc["weight"].sum()).round(3).to_string())
    return out


if __name__ == "__main__":
    derive_timeslots("city".replace("city", "tokyo"))