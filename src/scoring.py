"""Compute the photogenicity score per location.

photogenicity = 0.30*density_n + 0.45*engagement_n + 0.25*rating_n
  density    = log(1 + unique_owners)
  engagement = owner-averaged, recency-weighted mean of log(1+faves)
  rating     = google_rating / 5
All three normalized (min-max) within city. NULL if < 5 photos.
See docs/design.md for the reasoning and its three revisions.
"""

import numpy as np
import pandas as pd
from pathlib import Path

INTERIM_DIR = Path("data/interim")

W_DENSITY = 0.30
W_ENGAGEMENT = 0.45
W_RATING = 0.25

MIN_PHOTOS = 5
RECENCY_HALFLIFE_YEARS = 5
REFERENCE_YEAR = 2026


def _minmax(s):
    """Normalize a Series to 0..1, ignoring NaN. Flat series -> 0.5."""
    lo, hi = s.min(), s.max()
    if hi == lo:
        return pd.Series(0.5, index=s.index)
    return (s - lo) / (hi - lo)


def compute_scores(city):
    locs = pd.read_parquet(INTERIM_DIR / f"{city}_locations_enriched.parquet")
    pc = pd.read_parquet(INTERIM_DIR / f"{city}_photo_clusters.parquet")
    pc = pc[pc.cluster.isin(set(locs.cluster))].copy()

    # ---- DENSITY: log(1 + unique owners) ----
    density_raw = locs.set_index("cluster")["n_owners"].apply(lambda n: np.log1p(n))

    # ---- ENGAGEMENT: owner-averaged, recency-weighted mean of log(1+faves) ----
    pc["log_faves"] = np.log1p(pc["count_faves"].fillna(0))

    # recency weight per photo (photos with no valid date -> weight 1.0, neutral)
    yr = pc["datetaken"].dt.year
    age = (REFERENCE_YEAR - yr).clip(lower=0)
    pc["recency_w"] = np.where(yr.notna(), 0.5 ** (age / RECENCY_HALFLIFE_YEARS), 1.0)

    # Step 1: per (cluster, owner) — recency-weighted mean of log_faves.
    #         One value per owner, so prolific owners don't dominate.
    def wmean(g):
        w = g["recency_w"]
        return np.average(g["log_faves"], weights=w) if w.sum() > 0 else g["log_faves"].mean()

    per_owner = (pc.groupby(["cluster", "owner"], group_keys=False)
                   .apply(wmean, include_groups=False)
                   .rename("owner_score"))

    # Step 2: per cluster — mean across owners (one owner, one vote).
    engagement_raw = per_owner.groupby("cluster").mean()

    # ---- RATING: google_rating / 5 ----
    rating_raw = locs.set_index("cluster")["google_rating"] / 5.0

    # ---- assemble, apply min-5-photos floor, normalize, blend ----
    df = pd.DataFrame({
        "density_raw": density_raw,
        "engagement_raw": engagement_raw,
        "rating_raw": rating_raw,
    })
    df = locs.set_index("cluster").join(df)

    # min-photos floor: too few photos -> no trustworthy score
    df.loc[df["n_photos"] < MIN_PHOTOS, ["density_raw", "engagement_raw"]] = np.nan

    df["density_n"] = _minmax(df["density_raw"])
    df["engagement_n"] = _minmax(df["engagement_raw"])
    df["rating_n"] = _minmax(df["rating_raw"])

    # rating can be NaN (no Google match / no rating) — treat as neutral 0.5 so a
    # missing rating doesn't zero out an otherwise strong location.
    rating_filled = df["rating_n"].fillna(0.5)

    df["photogenicity"] = (
        W_DENSITY * df["density_n"]
        + W_ENGAGEMENT * df["engagement_n"]
        + W_RATING * rating_filled
    )
    # if density/engagement are NaN (below floor), score is NaN
    df.loc[df["density_n"].isna() | df["engagement_n"].isna(), "photogenicity"] = np.nan

    out = df.reset_index()
    out.to_parquet(INTERIM_DIR / f"{city}_scored.parquet", index=False)

    scored = out["photogenicity"].notna().sum()
    print(f"Scored {scored}/{len(out)} locations ({len(out)-scored} below floor / unscorable)")
    print("\nphotogenicity distribution:")
    print(out["photogenicity"].describe()[["min","25%","50%","75%","max"]].round(3).to_string())
    print("\ntop 15 by photogenicity:")
    print(out.nlargest(15, "photogenicity")[["name","photogenicity","n_owners","google_rating"]].to_string(index=False))
    return out


if __name__ == "__main__":
    compute_scores("tokyo")