"""Shoot Here — photography hotspot recommender (Tokyo).

Bare functional version: scenery + time-of-day filters -> ranked recommendations
on a map. Reads the SQLite database built by the pipeline.
"""

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).parent.parent / "db" / "hotspots.db"

SCENERY_LABELS = {
    "street": "Street",
    "architecture": "Architecture",
    "nature_parks": "Nature & parks",
    "waterfront": "Waterfront",
    "temples_shrines": "Temples & shrines",
    "neon_nightlife": "Neon & nightlife",
    "food": "Food",
}
TIME_LABELS = {
    "golden_hour": "Golden hour",
    "blue_hour": "Blue hour",
    "daytime": "Daytime",
    "night": "Night",
}


@st.cache_data
def load_options():
    """Which scenery buckets actually exist in the DB (excludes 'general')."""
    conn = sqlite3.connect(DB_PATH)
    tags = pd.read_sql("SELECT DISTINCT scenery_tag FROM location_tags", conn)
    conn.close()
    return [t for t in SCENERY_LABELS if t in set(tags.scenery_tag)]


def recommend(scenery, time_bucket, w_photo, limit=25):
    conn = sqlite3.connect(DB_PATH)
    q = """
    SELECT DISTINCT
        l.location_id, l.name, l.lat, l.lng,
        l.photogenicity, l.google_rating,
        ts.time_fit
    FROM locations l
    JOIN location_tags t       ON t.location_id = l.location_id
    JOIN location_timeslots ts ON ts.location_id = l.location_id
    WHERE t.scenery_tag = ?
      AND ts.time_bucket = ?
      AND l.photogenicity IS NOT NULL
    ORDER BY (? * l.photogenicity + ? * ts.time_fit) DESC
    LIMIT ?;
    """
    w_time = 1.0 - w_photo
    df = pd.read_sql(q, conn, params=(scenery, time_bucket, w_photo, w_time, limit))
    conn.close()
    return df


st.title("Shoot Here")
st.caption("Where to shoot in Tokyo — ranked by what people actually photograph, not just popularity.")

with st.expander("How we rank these spots"):
    st.markdown("""
    Every spot is scored from **265,000 geotagged Tokyo photos**, on three signals:

    - **How many *different* photographers shoot there.** We count distinct people, not
      photo volume — so a spot 400 people each shot once beats one that a single
      enthusiast photographed 1,000 times.
    - **How much those photos get favorited.** Favorites are a quality vote. We use a
      recency-weighted average, so a spot's score reflects what's photogenic *now*,
      not a decade ago.
    - **Its Google rating**, as an independent cross-check.

    **Time-of-day fit** compares each spot's best hours against the citywide average.
    Because most photos are taken in daylight, a spot that over-indexes at *golden hour*
    is genuinely special — so those rise to the top when you ask for it, instead of
    being buried under famous all-day landmarks.

    Use the **ranking balance** slider to weight overall quality against time-of-day fit.
    """)

options = load_options()

col1, col2 = st.columns(2)
with col1:
    scenery = st.selectbox("What do you want to shoot?",
                           options, format_func=lambda k: SCENERY_LABELS[k])
with col2:
    time_bucket = st.selectbox("When?",
                               list(TIME_LABELS), format_func=lambda k: TIME_LABELS[k])

w_photo = st.slider(
    "Ranking balance", 0.0, 1.0, 0.6, 0.1,
    help="Left = favor time-of-day fit. Right = favor overall photogenicity.",
)

df = recommend(scenery, time_bucket, w_photo)

if df.empty:
    st.info(f"No {SCENERY_LABELS[scenery].lower()} spots found for {TIME_LABELS[time_bucket].lower()}. Try a different combination.")
else:
    st.subheader(f"{len(df)} spots for {SCENERY_LABELS[scenery].lower()} at {TIME_LABELS[time_bucket].lower()}")
    st.map(df.rename(columns={"lat": "latitude", "lng": "longitude"}), size=60)
    st.dataframe(
        df[["name", "photogenicity", "time_fit", "google_rating"]].rename(columns={
            "name": "Spot", "photogenicity": "Score",
            "time_fit": "Time fit", "google_rating": "Google rating",
        }),
        hide_index=True, use_container_width=True,
    )