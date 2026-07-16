"""Merge cluster fragments that matched the same Google place_id.

DBSCAN (eps=50m) split some large venues into adjacent clusters that both
matched one POI. Remap each such group to a single canonical cluster ID in
photo_clusters, so downstream aggregations pool the evidence instead of
double-counting or discarding it.
"""

import pandas as pd
from pathlib import Path

INTERIM_DIR = Path("data/interim")


def merge_duplicate_clusters(city):
    scored = pd.read_parquet(INTERIM_DIR / f"{city}_scored.parquet")

    # place_id -> canonical cluster (keep the lowest cluster id in each dup group)
    dupes = scored[scored.place_id.notna() & scored.place_id.duplicated(keep=False)]
    remap = {}
    for pid, g in dupes.groupby("place_id"):
        canonical = int(g.cluster.min())
        for cid in g.cluster:
            if int(cid) != canonical:
                remap[int(cid)] = canonical
    print(f"Merging {len(remap)} fragment clusters into {dupes.place_id.nunique()} canonical locations")

    # Remap photo_clusters
    pc = pd.read_parquet(INTERIM_DIR / f"{city}_photo_clusters.parquet")
    pc["cluster"] = pc["cluster"].replace(remap)
    pc.to_parquet(INTERIM_DIR / f"{city}_photo_clusters.parquet", index=False)

    # Remap the locations table too, then collapse merged rows.
    # Recompute n_photos / n_owners from the remapped photos; keep place data
    # from the canonical row.
    locs = pd.read_parquet(INTERIM_DIR / f"{city}_locations_enriched.parquet")
    locs["cluster"] = locs["cluster"].replace(remap)

    agg = pc.groupby("cluster").agg(
        n_photos=("id", "size"),
        n_owners=("owner", "nunique"),
    )
    # keep the canonical row's place fields (name/rating/types/coords), drop dup rows
    locs = locs.drop_duplicates(subset="cluster", keep="first").set_index("cluster")
    locs["n_photos"] = agg["n_photos"]
    locs["n_owners"] = agg["n_owners"]
    locs = locs.reset_index()
    locs.to_parquet(INTERIM_DIR / f"{city}_locations_enriched.parquet", index=False)

    print(f"Locations after merge: {len(locs)}")
    return remap


if __name__ == "__main__":
    merge_duplicate_clusters("tokyo")