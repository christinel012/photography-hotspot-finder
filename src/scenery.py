"""Assign scenery buckets to locations from Flickr tags + Google place types.

Flickr tags are gated on distinct-owner count (not raw frequency) so one
tag-happy user can't assign a bucket. Google types anchor the buckets they
cover cleanly; tags carry street/architecture/waterfront and rescue the
~40% of locations Google labels only as transit.
"""

import pandas as pd
from pathlib import Path

INTERIM_DIR = Path("data/interim")

# Flickr tag keywords per bucket (grounded in observed tag frequencies; EN + JP).
TAG_KEYWORDS = {
    "nature_parks":   {"park", "nature", "garden", "flower", "plant", "sakura",
                       "momiji", "pond", "自然", "植物", "花", "公園", "庭園"},
    "street":         {"street", "streetphoto", "streetphotography", "walking",
                       "alley", "散歩", "ストリート", "路上写真", "ウォーキング"},
    "architecture":   {"architecture", "building", "skyscraper", "tower", "city",
                       "建築", "建物"},
    "neon_nightlife": {"night", "neon", "illumination", "nightscape", "夜景", "夜"},
    "waterfront":     {"river", "bridge", "bay", "sea", "harbor", "canal",
                       "海", "川", "橋", "運河"},
    "temples_shrines":{"temple", "shrine", "torii", "jinja", "sensoji", "meiji",
                       "pagoda", "寺", "神社", "鳥居"},
    "food":           {"food", "ramen", "sushi", "izakaya", "market", "屋台"},
}

# Google place types per bucket (clean anchors).
TYPE_KEYWORDS = {
    "nature_parks":   {"park", "garden", "national_park", "botanical_garden", "tea_house"},
    "temples_shrines":{"place_of_worship", "shinto_shrine", "buddhist_temple", "church"},
    "food":           {"restaurant", "food", "cafe", "japanese_restaurant",
                       "food_store", "coffee_shop", "bakery", "bar"},
    "neon_nightlife": {"bar", "night_club"},
    "waterfront":     {"bridge", "marina", "dam"}, # watergates/canals often tagged point_of_interest — tags still needed
    "architecture":   {"tourist_attraction", "observation_deck", "museum",
                       "art_museum", "historical_landmark", "historical_place",
                       "monument", "event_venue"},  
    # street: no reliable Google type — tags only
}

MIN_OWNERS_PER_BUCKET = 5   # distinct owners tagging a bucket keyword


def assign_buckets(city):
    locs = pd.read_parquet(INTERIM_DIR / f"{city}_locations_enriched.parquet")
    locs["types"] = locs["types"].apply(lambda ts: list(ts) if ts is not None else [])

    pc = pd.read_parquet(INTERIM_DIR / f"{city}_photo_clusters.parquet")

    # Build: for each (cluster, bucket), how many distinct owners used a keyword?
    bucket_rows = []
    for cluster, grp in pc.groupby("cluster"):
        for bucket, keywords in TAG_KEYWORDS.items():
            owners = set()
            for row in grp.itertuples():
                if not row.tags:
                    continue
                tags = set(str(row.tags).lower().split())
                if tags & keywords:
                    owners.add(row.owner)
            if len(owners) >= MIN_OWNERS_PER_BUCKET:
                bucket_rows.append({"cluster": cluster, "scenery_tag": bucket,
                                    "source": "flickr", "owner_support": len(owners)})

    # Google-type-driven buckets
    for r in locs.itertuples():
        loc_types = set(r.types)
        for bucket, type_kw in TYPE_KEYWORDS.items():
            if loc_types & type_kw:
                bucket_rows.append({"cluster": r.cluster, "scenery_tag": bucket,
                                    "source": "google", "owner_support": None})

    tags_df = pd.DataFrame(bucket_rows).drop_duplicates(subset=["cluster", "scenery_tag"])

    out = INTERIM_DIR / f"{city}_location_tags.parquet"
    tags_df.to_parquet(out, index=False)

    # Locations with no scenery signal from either source = transit/commercial noise.
    # Tag them 'general' so they're retained but excluded from scenery-filtered results.
    tagged_clusters = set(tags_df.cluster.unique())
    general = [{"cluster": c, "scenery_tag": "general", "source": "fallback",
               "owner_support": None}
              for c in locs.cluster if c not in tagged_clusters]
    if general:
        tags_df = pd.concat([tags_df, pd.DataFrame(general)], ignore_index=True)
        tags_df.to_parquet(out, index=False)
        print(f"\nTagged {len(general)} no-scenery locations as 'general' (retained, excluded from scenery filters)")

    # Summary
    print(f"Locations: {len(locs)}")
    print(f"Bucket assignments: {len(tags_df)}")
    print(f"Locations with >=1 bucket: {tags_df.cluster.nunique()}")
    print(f"Locations with NO bucket: {len(locs) - tags_df.cluster.nunique()}")
    print("\nassignments per bucket:")
    print(tags_df.scenery_tag.value_counts().to_string())
    print("\nbuckets per location:")
    print(tags_df.groupby('cluster').size().value_counts().sort_index().to_string())
    return tags_df


if __name__ == "__main__":
    assign_buckets("tokyo")