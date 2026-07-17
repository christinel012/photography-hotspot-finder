"""Shoot Here — photography hotspot recommender for Tokyo.

Single-file multipage Streamlit app (landing gate via session state):
  • Landing   — centered clickable title + About corner
  • Discover  — the recommender (multi-select scenery + time, ranked pastel cards)
  • Method    — narrative + math: the photogenicity model and its revisions
  • About     — bio, skills, links

Collage-diary aesthetic; card accent shifts with the selected time of day.
Descriptions are composed from each location's real attributes (no LLM) so every
claim is traceable to data.
"""

import sqlite3
import urllib.parse
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).parent.parent / "db" / "hotspots.db"

st.set_page_config(page_title="Shoot Here", page_icon="✦", layout="wide")

# ---- links (swap PORTFOLIO_URL to christineli.dev when live) ----
GITHUB_URL = "https://github.com/christinel012/photography-hotspot-finder"
GITHUB_PROFILE = "https://github.com/christinel012"
LINKEDIN_URL = "https://www.linkedin.com/in/christineli012"
EMAIL = "ytingli0210@gmail.com"
PORTFOLIO_URL = GITHUB_PROFILE  # TODO: point to christineli.dev when live

SCENERY_LABELS = {
    "street": "Street", "architecture": "Architecture", "nature_parks": "Nature & parks",
    "waterfront": "Waterfront", "temples_shrines": "Temples & shrines",
    "neon_nightlife": "Neon & nightlife", "food": "Food",
}
TIME_LABELS = {
    "golden_hour": "Golden hour", "blue_hour": "Blue hour",
    "daytime": "Daytime", "night": "Night",
}
TIME_THEME = {   # tile, tile_deep, motif
    "golden_hour": ("#FFE1C7", "#E88C3C", "☀"),
    "blue_hour":   ("#C7E9FF", "#5E6BC4", "✦"),
    "daytime":     ("#D4F4DD", "#4FA3D6", "❀"),
    "night":       ("#E8D9FF", "#7A5CB8", "★"),
}

# ===========================================================================
# Data
# ===========================================================================
@st.cache_data
def scenery_options():
    conn = sqlite3.connect(DB_PATH)
    rows = pd.read_sql("SELECT DISTINCT scenery_tag FROM location_tags", conn)
    conn.close()
    present = set(rows.scenery_tag)
    return [k for k in SCENERY_LABELS if k in present]


@st.cache_data
def tags_by_location():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        "SELECT location_id, scenery_tag FROM location_tags WHERE scenery_tag != 'general'", conn)
    conn.close()
    return df.groupby("location_id")["scenery_tag"].apply(list).to_dict()


def recommend(scenery_list, time_bucket, w_photo, limit=24):
    conn = sqlite3.connect(DB_PATH)
    placeholders = ",".join("?" for _ in scenery_list)
    w_time = 1.0 - w_photo
    q = f"""
    SELECT l.location_id, l.name, l.lat, l.lng,
           l.photogenicity, l.google_rating, l.flickr_photo_count,
           ts.time_fit,
           COUNT(DISTINCT t.scenery_tag) AS match_count
    FROM locations l
    JOIN location_tags t       ON t.location_id = l.location_id
    JOIN location_timeslots ts ON ts.location_id = l.location_id
    WHERE t.scenery_tag IN ({placeholders})
      AND ts.time_bucket = ?
      AND l.photogenicity IS NOT NULL
    GROUP BY l.location_id, l.name, l.lat, l.lng,
             l.photogenicity, l.google_rating, l.flickr_photo_count, ts.time_fit
    ORDER BY (? * l.photogenicity + ? * ts.time_fit
              + 0.05 * (COUNT(DISTINCT t.scenery_tag) - 1)) DESC
    LIMIT ?;
    """
    params = (*scenery_list, time_bucket, w_photo, w_time, limit)
    df = pd.read_sql(q, conn, params=params)
    conn.close()
    return df


# ===========================================================================
# Storytelling (all data-driven — no LLM, every clause traces to a value)
# ===========================================================================
def tier(score):
    if score >= 0.65: return "Exceptional"
    if score >= 0.45: return "Great"
    if score >= 0.30: return "Solid"
    return "Worth a look"


def fit_phrase(fit, time_label):
    t = time_label.lower()
    if fit >= 1.35: return f"especially good at {t}"
    if fit >= 1.10: return f"good at {t}"
    if fit >= 0.90: return "lovely any time of day"
    return "better at other times"


def describe(row, loc_tags, time_label):
    """Compose a one-sentence description from the location's real attributes.
    Phrasing adapts to which signal is strongest, so cards don't feel templated."""
    tags = [SCENERY_LABELS[t].lower() for t in loc_tags if t in SCENERY_LABELS]
    if len(tags) >= 2:
        scenery = f"{tags[0]} and {tags[1]}"
    elif tags:
        scenery = tags[0]
    else:
        scenery = "photogenic"

    fit = row.time_fit
    rating = f"rated {row.google_rating:.1f} on Google" if pd.notna(row.google_rating) else None

    # lead with the strongest signal
    if fit >= 1.35:
        lead = f"A {scenery} spot that's especially good at {time_label.lower()}"
    elif row.photogenicity >= 0.65:
        lead = f"One of Tokyo's standout {scenery} spots"
    elif row.flickr_photo_count and row.match_count and tier(row.photogenicity) in ("Great", "Solid"):
        lead = f"A quieter {scenery} spot worth seeking out"
    else:
        lead = f"A {scenery} spot"

    tail = f", {rating}." if rating else "."
    return lead + tail


def flickr_link(name):
    return f"https://www.flickr.com/search/?text={urllib.parse.quote(name + ' Tokyo')}"


def maps_link(lat, lng):
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"


# ===========================================================================
# Styling
# ===========================================================================
def inject_css():
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fredoka:wght@400;500;600;700&family=Nunito:wght@400;500;600;700&display=swap');
.stApp { background: #FFF9FB; }
html, body, [class*="css"] { font-family: 'Nunito', system-ui, sans-serif; }
h1,h2,h3,h4 { font-family: 'Fredoka', sans-serif !important; color: #4A4658 !important; }

.hero-title { font-family:'Fredoka',sans-serif; font-weight:700; font-size:46px; color:#4A4658; margin:0; line-height:1.1; position:relative; display:inline-block; }
.hero-title::after { content:'\\2726'; position:absolute; top:-6px; right:-28px; color:#FFA6C9; font-size:22px; }
.hero-sub { color:#8B879B; font-size:15px; margin:6px 0 0; }

/* home link — quiet, logo-like */
.stButton > button { border-radius: 999px; font-family:'Fredoka',sans-serif; border:1.5px solid #FFE1EC; color:#B06A99; background:#fff; }
.stButton > button:hover { border-color:#FFA6C9; color:#B06A99; }

/* landing */
.landing { text-align:center; padding:80px 20px 40px; }
.landing .big { font-family:'Fredoka',sans-serif; font-weight:700; font-size:74px; color:#4A4658; line-height:1.05; position:relative; display:inline-block; }
.landing .big::after { content:'\\2726'; position:absolute; top:2px; right:-38px; color:#FFA6C9; font-size:34px; }
.landing .tag { color:#8B879B; font-size:18px; margin-top:14px; }

/* cards */
.card-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:16px; margin-top:8px; }
.spot-card { border-radius:22px; padding:16px; position:relative; overflow:hidden; border:2px solid #fff; box-shadow:0 4px 14px rgba(74,70,88,.09); transition:transform .18s ease; }
.spot-card:hover { transform:rotate(-1deg) translateY(-3px); }
.spot-card::before { content:''; position:absolute; top:12px; left:-18px; width:58px; height:18px; background:rgba(255,255,255,.55); transform:rotate(-45deg); }
.inner { background:#fff; border-radius:14px; padding:13px 14px 14px; box-shadow:0 2px 6px rgba(74,70,88,.08); }
.rank { font-family:'Fredoka',sans-serif; font-size:12px; color:#8B879B; font-weight:500; }
.name { font-family:'Fredoka',sans-serif; font-weight:600; font-size:17px; color:#4A4658; margin:2px 0 6px; line-height:1.25; }
.desc { font-size:12.5px; color:#8B879B; min-height:52px; line-height:1.45; }
.meta { display:flex; gap:7px; margin-top:10px; align-items:center; flex-wrap:wrap; }
.badge { font-size:11px; font-weight:700; padding:4px 10px; border-radius:999px; color:#fff; }
.star { font-size:12px; color:#4A4658; font-weight:700; margin-left:auto; }
.links { display:flex; gap:12px; margin-top:10px; }
.links a { font-size:12px; font-weight:700; text-decoration:none; color:#B06A99; }
.links a:hover { text-decoration:underline; }
.sticker { position:absolute; bottom:8px; right:11px; font-size:15px; opacity:.8; }

/* method page equation block */
.eqn { background:#fff; border:2px solid #FFE1EC; border-radius:16px; padding:16px 18px; font-family:'Nunito',monospace; color:#4A4658; margin:12px 0; }
.eqn b { color:#B06A99; }
.callout { background:#F6EEFF; border-left:4px solid #C7A6F0; border-radius:0 12px 12px 0; padding:12px 16px; margin:12px 0; color:#5B5470; font-size:14px; }

/* about */
.about-chip { display:inline-block; background:#FFE1EC; color:#B06A99; font-weight:700; font-size:12.5px; padding:5px 12px; border-radius:999px; margin:3px 4px 3px 0; }
.about-lead { font-size:16px; color:#5B5470; line-height:1.6; }

.stMultiSelect [data-baseweb="tag"] { background:#FFA6C9 !important; border-radius:999px !important; }
div[data-testid="stExpander"] details { border:1px solid #F2E4EE !important; border-radius:14px !important; background:#fff !important; }
</style>
""", unsafe_allow_html=True)


# ===========================================================================
# Pages
# ===========================================================================
def home_link():
    if st.button("‹ Shoot Here", key=f"home_{st.session_state.page}"):
        st.session_state.page = "landing"; st.rerun()

def nav():
    cols = st.columns([1, 1, 1, 6])
    if cols[0].button("✦ Discover", use_container_width=True):
        st.session_state.page = "discover"; st.rerun()
    if cols[1].button("How it works", use_container_width=True):
        st.session_state.page = "method"; st.rerun()
    if cols[2].button("About", use_container_width=True):
        st.session_state.page = "about"; st.rerun()
    st.write("")


def page_landing():
    st.markdown("""
    <div class="landing">
      <div class="big">Shoot Here</div>
      <div class="tag">Find the best places to shoot, ranked by what people<br>actually photograph — not just what's popular.<br><span style="font-size:14px;opacity:.75;">Starting with Tokyo. More cities on the way.</span></div>
    """, unsafe_allow_html=True)
    c1, c2, c3 = st.columns([2, 1, 2])
    with c2:
        if st.button("Start exploring  →", use_container_width=True):
            st.session_state.page = "discover"; st.rerun()
    st.write("")
    a1, a2, a3 = st.columns([2, 1, 2])
    with a2:
        if st.button("About the maker", use_container_width=True):
            st.session_state.page = "about"; st.rerun()


def page_discover():
    home_link()
    st.markdown('<div class="hero-title">Shoot Here</div>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">A little guide to a city\'s most photogenic corners — '
                'starting with Tokyo. ✿</p>', unsafe_allow_html=True)
    nav()

    with st.expander("How we rank these spots"):
        st.markdown("""
            Every spot is scored from **265,000 geotagged photos** (Tokyo is the first city — the
            pipeline is city-agnostic, so more are on the way), on three signals: 
            **how many *different* photographers shoot there** (distinct people, not photo volume),
            **how much their photos get favorited** (a recency-weighted quality vote), and its
            **Google rating** as a cross-check. **Time-of-day fit** compares a spot's best hours
            against the citywide average, so a place that over-indexes at *golden hour* rises when
            you ask for it. For the full method and the equations, see **How it works**.
        """)

    opts = scenery_options()
    c1, c2 = st.columns([2, 1])
    with c1:
        scenery = st.multiselect("What do you want to shoot?", opts,
                                 default=["street"], format_func=lambda k: SCENERY_LABELS[k])
    with c2:
        time_bucket = st.selectbox("When?", list(TIME_LABELS),
                                   format_func=lambda k: TIME_LABELS[k])

    w_photo = st.slider("Ranking balance", 0.0, 1.0, 0.6, 0.1, label_visibility="collapsed")
    st.caption(
        "**← Drag left** to surface spots that are *special at your chosen time* "
        "(hidden golden-hour gems). **Drag right →** for the most photogenic spots "
        "*overall*, regardless of time. The middle blends both."
    )
    show_map = st.toggle("Show map", value=False)

    if not scenery:
        st.info("Pick at least one thing you'd like to shoot, and I'll find the best spots for it.")
        return

    df = recommend(scenery, time_bucket, w_photo)
    loc_tags = tags_by_location()
    labels = ", ".join(SCENERY_LABELS[s].lower() for s in scenery)
    st.markdown(f"#### {len(df)} spots for {labels} at {TIME_LABELS[time_bucket].lower()}")

    if df.empty:
        st.info("No spots match that combination yet. Try another time of day or scenery.")
        return

    if show_map:
        st.map(df.rename(columns={"lat": "latitude", "lng": "longitude"}), size=60)

    tile, tile_deep, motif = TIME_THEME[time_bucket]
    tlabel = TIME_LABELS[time_bucket]
    cards = []
    for i, r in enumerate(df.itertuples(), start=1):
        rating = f"★ {r.google_rating:.1f}" if pd.notna(r.google_rating) else ""
        desc = describe(r, loc_tags.get(r.location_id, []), tlabel)
        cards.append(f"""
        <div class="spot-card" style="background:{tile};">
          <div class="inner">
            <div class="rank">#{i}</div>
            <div class="name">{r.name}</div>
            <div class="desc">{desc}</div>
            <div class="meta">
              <span class="badge" style="background:{tile_deep};">{tier(r.photogenicity)}</span>
              <span class="star">{rating}</span>
            </div>
            <div class="links">
              <a href="{flickr_link(r.name)}" target="_blank">See photos ↗</a>
              <a href="{maps_link(r.lat, r.lng)}" target="_blank">Map ↗</a>
            </div>
          </div>
          <span class="sticker">{motif}</span>
        </div>""")
    st.markdown(f'<div class="card-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def page_method():
    home_link()
    st.markdown('<div class="hero-title">How it works</div>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">The model behind the recommendations, and how it '
                'was corrected by looking at the data. ✎</p>', unsafe_allow_html=True)
    nav()

    st.markdown("### The photogenicity score")
    st.markdown(
        "Every location gets a single score blending three signals, each normalized "
        "within the city so one dimension can't dominate:")
    st.markdown("""
<div class="eqn">
photogenicity = <b>0.30</b>·density + <b>0.45</b>·engagement + <b>0.25</b>·rating
</div>
""", unsafe_allow_html=True)
    st.markdown("""
- **Density** — `log(1 + unique_owners)`. How many *distinct* photographers shoot here.
- **Engagement** *(weighted highest)* — an owner-averaged, recency-weighted mean of
  `log(1 + favorites)`. The quality signal that stops the score from becoming a
  popularity map.
- **Rating** — the Google rating, as an independent cross-check the photo data can't game.
    """)

    st.markdown("### Three fixes the data forced")
    st.markdown("""
This is a data project, so the interesting part isn't the formula — it's the three
times the first version was wrong, and looking at the data showed why.
    """)
    st.markdown("""
<div class="callout"><b>1 · Median → log-mean.</b> The engagement term first used the
<i>median</i> favorites per location — the textbook robust choice for skewed data. But
favorites are <i>zero-inflated</i>: 57% of photos have zero, and the per-location median
was 0 for 56% of locations, making the highest-weighted term a near-constant. Switched to
the mean of log(1+favorites): outlier-resistance now comes from the log, not the median.</div>
""", unsafe_allow_html=True)
    st.markdown("""
<div class="callout"><b>2 · Photo count → unique owners.</b> Ranking by raw photo count
surfaced a spot with 1,000 photos from a <i>single</i> owner (someone's home) and
plane-spotter fences near Haneda. Genuine hotspots show many <i>different</i> photographers
at a few photos each — so density counts distinct owners, not photos.</div>
""", unsafe_allow_html=True)
    st.markdown("""
<div class="callout"><b>3 · Time fit, normalized.</b> Two-thirds of all photos are taken
in daylight, so raw time shares always favor daytime. Time-of-day fit is normalized against
the citywide baseline for each hour — so a spot that over-indexes at golden hour (rare, ~7%
of photos) rises to the top when you ask for it, instead of being buried under famous
all-day landmarks.</div>
""", unsafe_allow_html=True)

    st.markdown("### From photos to spots")
    st.markdown("""
Starting with Tokyo, photos were clustered by location (DBSCAN on coordinates), filtered
to spots with many distinct photographers, matched to Google Places for names and ratings,
and tagged into seven scenery types. The whole pipeline is **city-agnostic** — a city is a
config value, not hardcoded — so adding the next city is re-running it with a new bounding
box. A recommendation is a live SQL query joining all of it.
    """)
    st.markdown(f"[See the full source and write-up on GitHub ↗]({GITHUB_URL})")


def page_about():
    home_link()
    st.markdown('<div class="hero-title">About</div>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">The maker behind Shoot Here. ♡</p>', unsafe_allow_html=True)
    nav()

    left, right = st.columns([3, 2])
    with left:
        st.markdown("## Christine Li")
        st.markdown("**Statistics @ UC Davis · Master of Analytics @ UC Berkeley**")
        st.markdown("""
<p class="about-lead">
I build data projects at the intersection of rigorous analysis and product thinking.
Shoot Here is one of two solo portfolio projects I built end-to-end — full data pipeline,
scoring model, and a product-quality interface — to show what I can do independently.
</p>
<p class="about-lead">
Open to <b>Data Analytics</b>, <b>AI Product</b>, and <b>Machine Learning</b> roles —
internships, new grad, and full-time.
</p>
        """, unsafe_allow_html=True)
        st.markdown(
            f"[GitHub ↗]({GITHUB_PROFILE})  ·  [LinkedIn ↗]({LINKEDIN_URL})  ·  "
            f"[Email](mailto:{EMAIL})  ·  [Portfolio ↗]({PORTFOLIO_URL})")
    with right:
        st.markdown("##### This project")
        st.markdown("""
<div class="callout">
Built solo. 264,000 geotagged Flickr photos (Tokyo first, city-agnostic by design) →
spatial clustering → Google Places enrichment → a three-signal photogenicity model
(revised three times from the data) → a SQLite backend → this Streamlit app. Full source on GitHub.
</div>
        """, unsafe_allow_html=True)
        st.markdown("##### Skills")
        st.markdown("##### Skills")
        skill_groups = {
            "Languages": ["Python", "SQL", "R"],
            "Data & ML": ["Pandas", "GeoPandas", "scikit-learn", "DBSCAN"],
            "Backend & viz": ["SQLite", "Streamlit", "Plotly"],
            "APIs & tools": ["Flickr API", "Google Places API", "Git"],
        }
        for group, items in skill_groups.items():
            chips = "".join(f'<span class="about-chip">{s}</span>' for s in items)
            st.markdown(
                f'<div style="margin-bottom:10px;"><div style="font-size:11px;'
                f'font-weight:700;color:#B06A99;letter-spacing:.5px;'
                f'text-transform:uppercase;margin-bottom:4px;">{group}</div>{chips}</div>',
                unsafe_allow_html=True)


# ===========================================================================
# Router
# ===========================================================================
inject_css()
if "page" not in st.session_state:
    st.session_state.page = "landing"

page = st.session_state.page
if page == "landing":
    page_landing()
elif page == "discover":
    page_discover()
elif page == "method":
    page_method()
elif page == "about":
    page_about()