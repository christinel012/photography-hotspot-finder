-- Photography Hotspot Finder — database schema
-- SQLite first (see docs/design.md). Written in standard SQL where possible;
-- portability notes to Postgres are flagged inline.
--
-- SQLite does not enforce foreign keys unless this is set per-connection:
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- locations — intrinsic core. One row per photographable spot.
-- ---------------------------------------------------------------------------
CREATE TABLE locations (
    location_id      INTEGER PRIMARY KEY,          -- Postgres: GENERATED ALWAYS AS IDENTITY
    source_place_id  TEXT UNIQUE,                  -- Google Place ID; dedup key on ingest
    city             TEXT    NOT NULL,             -- city-agnostic: never hardcoded in code
    name             TEXT    NOT NULL,
    lat              REAL    NOT NULL,
    lng              REAL    NOT NULL,
    is_outdoor       INTEGER NOT NULL DEFAULT 1    -- 0/1 (SQLite has no BOOLEAN)
                     CHECK (is_outdoor IN (0, 1)),

    -- raw scoring inputs (kept so photogenicity can be recomputed)
    flickr_photo_count  INTEGER NOT NULL DEFAULT 0,
    flickr_engagement   REAL,                      -- median favorites per photo
    google_rating       REAL CHECK (google_rating BETWEEN 0 AND 5),

    -- final composite score, normalized within city.
    -- NULL when flickr_photo_count < 5 (too few photos to trust engagement).
    photogenicity       REAL CHECK (photogenicity BETWEEN 0 AND 1)
);

CREATE INDEX idx_locations_city ON locations (city);

-- ---------------------------------------------------------------------------
-- location_tags — many-to-many scenery tags. A spot can hold several buckets.
-- ---------------------------------------------------------------------------
CREATE TABLE location_tags (
    location_id  INTEGER NOT NULL
                 REFERENCES locations (location_id) ON DELETE CASCADE,
    scenery_tag  TEXT    NOT NULL
                 CHECK (scenery_tag IN (
                     'street',           -- daytime urban
                     'architecture',
                     'nature_parks',
                     'waterfront',
                     'temples_shrines',
                     'neon_nightlife',   -- illuminated night scenes
                     'food',
                     'general'
                 )),
    PRIMARY KEY (location_id, scenery_tag)
);

CREATE INDEX idx_tags_scenery ON location_tags (scenery_tag);

-- ---------------------------------------------------------------------------
-- location_timeslots — derived time-of-day suitability, per bucket.
-- ---------------------------------------------------------------------------
CREATE TABLE location_timeslots (
    location_id  INTEGER NOT NULL
                 REFERENCES locations (location_id) ON DELETE CASCADE,
    time_bucket  TEXT    NOT NULL
                 CHECK (time_bucket IN (
                     'golden_hour', 'blue_hour', 'night', 'daytime'
                 )),
    suitability  REAL    NOT NULL
                 CHECK (suitability BETWEEN 0 AND 1),
    PRIMARY KEY (location_id, time_bucket)
);

-- ---------------------------------------------------------------------------
-- conditions — contextual crowd/weather snapshots. Optional in v1
-- (may call the weather API live instead of storing rows here).
-- ---------------------------------------------------------------------------
CREATE TABLE conditions (
    location_id  INTEGER NOT NULL
                 REFERENCES locations (location_id) ON DELETE CASCADE,
    captured_at  TEXT    NOT NULL,                 -- ISO-8601; Postgres: TIMESTAMPTZ
    crowd_level  INTEGER CHECK (crowd_level BETWEEN 0 AND 100),  -- Google popular-times value
    weather      TEXT,                             -- e.g. 'clear', 'rain', 'clouds'
    PRIMARY KEY (location_id, captured_at)
);
