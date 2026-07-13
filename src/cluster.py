"""Cluster geotagged photos into candidate locations via DBSCAN."""

import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.cluster import DBSCAN

INTERIM_DIR = Path("data/interim")
EARTH_RADIUS_M = 6_371_000

EPS_METERS = 50
MIN_SAMPLES = 20


def cluster_photos(city, eps_m=EPS_METERS, min_samples=MIN_SAMPLES):
    df = pd.read_parquet(INTERIM_DIR / f"{city}_photos.parquet")

    coords = np.radians(df[["latitude", "longitude"]].to_numpy())
    eps_rad = eps_m / EARTH_RADIUS_M

    db = DBSCAN(eps=eps_rad, min_samples=min_samples, metric="haversine", algorithm="ball_tree")
    df["cluster"] = db.fit_predict(coords)

    n_clusters = df.cluster.nunique() - (1 if -1 in df.cluster.values else 0)
    n_noise = (df.cluster == -1).sum()
    print(f"eps={eps_m}m  min_samples={min_samples}")
    print(f"  clusters: {n_clusters:,}")
    print(f"  noise:    {n_noise:,} ({n_noise/len(df):.1%} of photos)")
    print(f"  clustered:{len(df)-n_noise:,}")

    return df


if __name__ == "__main__":
    cluster_photos("tokyo")


MIN_OWNERS = 10


def build_locations(city, eps_m=EPS_METERS, min_samples=MIN_SAMPLES, min_owners=MIN_OWNERS):
    """Cluster photos and aggregate into candidate locations."""
    df = cluster_photos(city, eps_m=eps_m, min_samples=min_samples)
    c = df[df.cluster != -1].copy()

    locs = c.groupby("cluster").agg(
        n_photos=("id", "size"),
        n_owners=("owner", "nunique"),
        lat=("latitude", "mean"),
        lng=("longitude", "mean"),
    )

    before = len(locs)
    locs = locs[locs.n_owners >= min_owners]
    print(f"Dropped {before - len(locs):,} clusters with < {min_owners} owners")
    print(f"Locations: {len(locs):,}")

    locs["city"] = city
    out = INTERIM_DIR / f"{city}_locations.parquet"
    locs.reset_index().to_parquet(out, index=False)

    # photo -> location mapping, for scoring
    c[["id", "cluster", "owner", "count_faves", "datetaken", "tags"]].to_parquet(
        INTERIM_DIR / f"{city}_photo_clusters.parquet", index=False
    )
    print(f"Wrote {out}")
    return locs