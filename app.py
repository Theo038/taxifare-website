# app.py
import os
import time
import math
import requests
import streamlit as st
from datetime import datetime, time as tm
import folium
from streamlit_folium import st_folium

# =========================
# PAGE CONFIG + STYLE
# =========================
st.set_page_config(page_title="NY Taxi App", page_icon="🚕", layout="wide")

# Hide Streamlit toolbar / badge / footer
st.markdown(
    """
    <style>
    div[data-testid="stToolbar"] { visibility: hidden; height: 0px; }
    div[data-testid="stDecoration"] { visibility: hidden; height: 0px; }
    div[data-testid="stStatusWidget"] { visibility: hidden; height: 0px; }
    .stAppDeployButton { display:none !important; }
    footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<h2>🚕 NY Taxi App — Autocomplete + OSRM Routing</h2>', unsafe_allow_html=True)
st.markdown(
    '<div>Type addresses or click the map. The <b>nearest marker</b> (pickup/dropoff) moves to your click. '
    'With a <b>LocationIQ</b> token, you’ll get live <b>autocomplete</b>.</div>',
    unsafe_allow_html=True,
)
st.markdown("<hr>", unsafe_allow_html=True)

# =========================
# CONSTANTS (OSRM & Fare API)
# =========================
OSRM_SERVER = "https://router.project-osrm.org"      # demo server
PROFILE = "driving"                                   # fixed profile
DEFAULT_FARE_API = "https://taxifare.lewagon.ai/predict"
NYC_VIEWBOX = (-74.259, 40.477, -73.700, 40.917)      # lon/lat bbox NYC
LOCATIONIQ_TOKEN = os.getenv("LOCATIONIQ_TOKEN")      # set this for live autocomplete

with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    fare_api_url = st.text_input("Fare prediction endpoint (GET)", value=DEFAULT_FARE_API)
    if LOCATIONIQ_TOKEN:
        st.success("LocationIQ token detected — live autocomplete enabled.")
    else:
        st.info("No LocationIQ token — use 'Search suggestions' button for compliant Nominatim lookups.")

# =========================
# SESSION STATE
# =========================
def init_state():
    # NYC defaults
    if "pickup" not in st.session_state:
        st.session_state.pickup = {"lat": 40.7580, "lng": -73.9855}   # Times Square
    if "dropoff" not in st.session_state:
        st.session_state.dropoff = {"lat": 40.7676, "lng": -73.9817}  # Central Park South
    if "pickup_address" not in st.session_state:
        st.session_state.pickup_address = "Times Square, New York, NY"
    if "dropoff_address" not in st.session_state:
        st.session_state.dropoff_address = "Central Park South, New York, NY"
    if "last_click" not in st.session_state:
        st.session_state.last_click = None
    # Autocomplete state
    if "pickup_query" not in st.session_state:
        st.session_state.pickup_query = st.session_state.pickup_address
    if "dropoff_query" not in st.session_state:
        st.session_state.dropoff_query = st.session_state.dropoff_address
    if "pickup_suggestions" not in st.session_state:
        st.session_state.pickup_suggestions = []
    if "dropoff_suggestions" not in st.session_state:
        st.session_state.dropoff_suggestions = []
    if "last_autocomplete_time" not in st.session_state:
        st.session_state.last_autocomplete_time = 0.0

init_state()

# =========================
# PROVIDERS — Autocomplete & Geocoding
# =========================
@st.cache_data(ttl=600, show_spinner=False)
def autocomplete_locationiq(q: str, limit=6, countrycodes="us", viewbox=NYC_VIEWBOX, bounded=1):
    """
    LocationIQ Autocomplete (type-ahead, supports substrings).
    https://api.locationiq.com/v1/autocomplete?key=TOKEN&q=SEARCH  (docs)
    """
    if not LOCATIONIQ_TOKEN:
        return []
    url = "https://api.locationiq.com/v1/autocomplete"
    params = {
        "key": LOCATIONIQ_TOKEN,
        "q": q,
        "limit": limit,
        "countrycodes": countrycodes,
        "viewbox": f"{viewbox[0]},{viewbox[1]},{viewbox[2]},{viewbox[3]}",
        "bounded": bounded,
        "accept-language": "en"
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    out = []
    for item in data:
        label = item.get("display_name") or item.get("address", "")
        lat = float(item.get("lat"))
        lng = float(item.get("lon"))
        out.append({"label": label, "lat": lat, "lng": lng})
    return out

@st.cache_data(ttl=600, show_spinner=False)
def search_nominatim(q: str, limit=5, countrycodes="us", viewbox=NYC_VIEWBOX, bounded=1):
    """
    Nominatim Search (manual suggestions). Compliant: no per-keystroke autocomplete on public server.
    https://nominatim.openstreetmap.org/search?format=jsonv2&...  (docs/policy)
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": q,
        "format": "jsonv2",
        "limit": limit,
        "countrycodes": countrycodes,
        "viewbox": f"{viewbox[0]},{viewbox[1]},{viewbox[2]},{viewbox[3]}",
        "bounded": bounded,
        "accept-language": "en"
    }
    headers = {"User-Agent": "ny-taxi-app/1.0 (contact: user@example.com)"}
    resp = requests.get(url, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    out = []
    for item in data:
        label = item.get("display_name", q)
        lat = float(item["lat"]); lng = float(item["lon"])
        out.append({"label": label, "lat": lat, "lng": lng})
    return out

# =========================
# UI — Addresses with Autocomplete
# =========================
left, right = st.columns([0.48, 0.52])

with left:
    st.markdown("### 🎛️ Trip parameters")
    c_dt1, c_dt2 = st.columns(2)
    trip_date = c_dt1.date_input("Date", value=datetime.now().date())
    trip_time = c_dt2.time_input("Time", value=tm(12, 0))

    # --- Pickup autocomplete ---
    st.markdown("#### 📍 Pickup")
    st.session_state.pickup_query = st.text_input(
        "Pickup address",
        value=st.session_state.pickup_query,
        placeholder="e.g., 1600 Broadway, New York, NY",
        key="pickup_query_input",
    )

    # live suggestions if LocationIQ token is present (throttle to ~0.6s)
    if LOCATIONIQ_TOKEN and len(st.session_state.pickup_query.strip()) >= 3:
        now = time.time()
        if now - st.session_state.last_autocomplete_time > 0.6:
            try:
                st.session_state.pickup_suggestions = autocomplete_locationiq(st.session_state.pickup_query)
                st.session_state.last_autocomplete_time = now
            except Exception as e:
                st.session_state.pickup_suggestions = []
                st.warning(f"Pickup autocomplete error: {e}")

    # manual compliant search if no token
    if not LOCATIONIQ_TOKEN:
        if st.button("🔎 Search pickup suggestions"):
            try:
                st.session_state.pickup_suggestions = search_nominatim(st.session_state.pickup_query)
            except Exception as e:
                st.session_state.pickup_suggestions = []
                st.error(f"Pickup search failed: {e}")

    if st.session_state.pickup_suggestions:
        labels = [s["label"] for s in st.session_state.pickup_suggestions]
        sel = st.selectbox("Suggestions (pickup)", labels, index=0, key="pickup_suggestions_select")
        if sel:
            choice = next((s for s in st.session_state.pickup_suggestions if s["label"] == sel), None)
            if choice:
                st.session_state.pickup = {"lat": choice["lat"], "lng": choice["lng"]}
                st.session_state.pickup_address = choice["label"]
                st.rerun()

    # --- Dropoff autocomplete ---
    st.markdown("#### 🏁 Dropoff")
    st.session_state.dropoff_query = st.text_input(
        "Dropoff address",
        value=st.session_state.dropoff_query,
        placeholder="e.g., 10 Columbus Cir, New York, NY",
        key="dropoff_query_input",
    )

    if LOCATIONIQ_TOKEN and len(st.session_state.dropoff_query.strip()) >= 3:
        now = time.time()
        if now - st.session_state.last_autocomplete_time > 0.6:
            try:
                st.session_state.dropoff_suggestions = autocomplete_locationiq(st.session_state.dropoff_query)
                st.session_state.last_autocomplete_time = now
            except Exception as e:
                st.session_state.dropoff_suggestions = []
                st.warning(f"Dropoff autocomplete error: {e}")

    if not LOCATIONIQ_TOKEN:
        if st.button("🔎 Search dropoff suggestions"):
            try:
                st.session_state.dropoff_suggestions = search_nominatim(st.session_state.dropoff_query)
            except Exception as e:
                st.session_state.dropoff_suggestions = []
                st.error(f"Dropoff search failed: {e}")

    if st.session_state.dropoff_suggestions:
        labels = [s["label"] for s in st.session_state.dropoff_suggestions]
        sel = st.selectbox("Suggestions (dropoff)", labels, index=0, key="dropoff_suggestions_select")
        if sel:
            choice = next((s for s in st.session_state.dropoff_suggestions if s["label"] == sel), None)
            if choice:
                st.session_state.dropoff = {"lat": choice["lat"], "lng": choice["lng"]}
                st.session_state.dropoff_address = choice["label"]
                st.rerun()

    # Passengers
    passenger_count = st.slider("👥 Passengers", min_value=1, max_value=6, value=1)

    st.markdown("<hr>", unsafe_allow_html=True)
    cta1, cta2 = st.columns([2, 1])
    with cta1:
        predict_now = st.button("🚗 Request a driver", type="primary")
    with cta2:
        reset = st.button("🧹 Reset points")
    if reset:
        st.session_state.pickup = {"lat": 40.7580, "lng": -73.9855}
        st.session_state.dropoff = {"lat": 40.7676, "lng": -73.9817}
        st.session_state.pickup_address = "Times Square, New York, NY"
        st.session_state.dropoff_address = "Central Park South, New York, NY"
        st.session_state.pickup_query = st.session_state.pickup_address
        st.session_state.dropoff_query = st.session_state.dropoff_address
        st.session_state.pickup_suggestions = []
        st.session_state.dropoff_suggestions = []
        st.session_state.last_click = None
        st.rerun()

# =========================
# MAP + CLICK-TO-MOVE
# =========================
with right:
    st.markdown("### 🗺️ Interactive map")
    center_lat = (st.session_state.pickup["lat"] + st.session_state.dropoff["lat"]) / 2
    center_lng = (st.session_state.pickup["lng"] + st.session_state.dropoff["lng"]) / 2

    m = folium.Map(location=[center_lat, center_lng], zoom_start=13, tiles="CartoDB positron")

    folium.Marker(
        [st.session_state.pickup["lat"], st.session_state.pickup["lng"]],
        popup=f"Pickup:<br>{st.session_state.pickup_address}",
        icon=folium.Icon(color="green", icon="play")
    ).add_to(m)
