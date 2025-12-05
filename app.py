
# app.py
import math
import requests
import streamlit as st
from datetime import datetime, time
import folium
from streamlit_folium import st_folium

# =========================
# PAGE CONFIG + STYLE
# =========================
st.set_page_config(page_title="NY Taxi App", page_icon="🚕", layout="wide")

# Hide Streamlit toolbar / "Manage app" badge / footer decorations
st.markdown("""
<style>
/* Hide the Streamlit main toolbar (top-right) and bottom decoration/badge */
div[data-testid="stToolbar"] { visibility: hidden; height: 0px; }        /* top toolbar */
div[data-testid="stDecoration"] { visibility: hidden; height: 0px; }     /* bottom decoration */
div[data-testid="stStatusWidget"] { visibility: hidden; height: 0px; }   /* status widget */
.stAppDeployButton { display:none !important; }                           /* deploy/manage. The <b>nearest marker</b> (pickup/dropoff) moves to your click.</div>', unsafe_allow_html=True).stAppDeployButton { display:none !important; }                           /* deploy/manage button */
st.markdown("<hr>", unsafe_allow_html=True)

# =========================
# CONSTANTS (fixed OSRM profile & endpoints)
# =========================
OSRM_SERVER = "https://router.project-osrm.org"   # demo server (testing)
PROFILE = "driving"                               # always driving
DEFAULT_FARE_API = "https://taxifare.lewagon.ai/predict"

with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    fare_api_url = st.text_input("Fare prediction endpoint (GET)", value=DEFAULT_FARE_API)
    st.info("OSRM demo server is rate-limited (429 possible) and provides no SLA. Avoid spamming.")

# =========================
# SESSION STATE
# =========================
def init_state():
    # NYC defaults
    if "pickup" not in st.session_state:
        # Times Square
        st.session_state.pickup = {"lat": 40.7580, "lng": -73.9855}
    if "dropoff" not in st.session_state:
        # Central Park South
        st.session_state.dropoff = {"lat": 40.7676, "lng": -73.9817}
    if "last_click" not in st.session_state:
        st.session_state.last_click = None

init_state()

# =========================
# UI CONTROLS
# =========================
left, right = st.columns([0.38, 0.62])

with left:
    st.markdown("### 🎛️ Trip parameters")
    c_dt1, c_dt2 = st.columns(2)
    trip_date = c_dt1.date_input("Date", value=datetime.now().date())
    trip_time = c_dt2.time_input("Time", value=time(12, 0))

    st.markdown("#### 📍 Pickup")
    p1, p2 = st.columns(2)
    pickup_lat = p1.number_input("Pickup latitude", value=float(st.session_state.pickup["lat"]), format="%.6f")
    pickup_lng = p2.number_input("Pickup longitude", value=float(st.session_state.pickup["lng"]), format="%.6f")
    if st.button("🔄 Update map from pickup"):
        st.session_state.pickup = {"lat": float(pickup_lat), "lng": float(pickup_lng)}
        st.rerun()

    st.markdown("#### 🏁 Dropoff")
    d1, d2 = st.columns(2)
    dropoff_lat = d1.number_input("Dropoff latitude", value=float(st.session_state.dropoff["lat"]), format="%.6f")
    dropoff_lng = d2.number_input("Dropoff longitude", value=float(st.session_state.dropoff["lng"]), format="%.6f")
    if st.button("🔄 Update map from dropoff"):
        st.session_state.dropoff = {"lat": float(dropoff_lat), "lng": float(dropoff_lng)}
        st.rerun()

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
        st.session_state.last_click = None
        st.rerun()

with right:
    st.markdown("### 🗺️ Interactive map")
    center_lat = (st.session_state.pickup["lat"] + st.session_state.dropoff["lat"]) / 2
    center_lng = (st.session_state.pickup["lng"] + st.session_state.dropoff["lng"]) / 2

    # Pretty light basemap (reliable alias; no attribution error)
    m = folium.Map(location=[center_lat, center_lng], zoom_start=13, tiles="CartoDB positron")

    # Markers
    folium.Marker(
        [st.session_state.pickup["lat"], st.session_state.pickup["lng"]],
        popup="Pickup",
        icon=folium.Icon(color="green", icon="play")
    ).add_to(m)
    folium.Marker(
        [st.session_state.dropoff["lat"], st.session_state.dropoff["lng"]],
        popup="Dropoff",
        icon=folium.Icon(color="red", icon="flag")
    ).add_to(m)

    # Light straight line (placeholder before OSRM route)
    folium.PolyLine(
        locations=[
            [st.session_state.pickup["lat"], st.session_state.pickup["lng"]],
            [st.session_state.dropoff["lat"], st.session_state.dropoff["lng"]],
        ],
        color="#bbb", weight=2, opacity=0.5
    ).add_to(m)

    # Render + capture clicks (defensive access to the click structure)
    map_data = st_folium(
        m, height=540, width=820,
        key="uber_map_nyc",
        returned_objects=[]
    )

    # --- Robust click handler: move the nearest marker to the clicked point ---
    click = (map_data or {}).get("last_clicked")
    if click:
        try:
            click_lat = float(click.get("lat"))
            click_lng = float(click.get("lng"))
        except (TypeError, ValueError):
            click_lat = click_lng = None

        if click_lat is not None and click_lng is not None:
            last = st.session_state.last_click
            # Only react if the click changed
            if last is None or (abs(last[0] - click_lat) > 1e-10 or abs(last[1] - click_lng) > 1e-10):
                st.session_state.last_click = (click_lat, click_lng)
                # Move the NEAREST marker (intuitive, no mode buttons)
                d_pick = math.hypot(click_lat - st.session_state.pickup["lat"], click_lng - st.session_state.pickup["lng"])
                d_drop = math.hypot(click_lat - st.session_state.dropoff["lat"], click_lng - st.session_state.dropoff["lng"])
                if d_pick <= d_drop:
                    st.session_state.pickup = {"lat": click_lat, "lng": click_lng}
                else:
                    st.session_state.dropoff = {"lat": click_lat, "lng": click_lng}
                st.rerun()

# =========================
# HELPERS & OSRM
# =========================
@st.cache_data(show_spinner=False, ttl=300)
def call_osrm_route(server, profile, p_lat, p_lng, d_lat, d_lng):
    """
    Call OSRM /route and return: distance_km, duration_min, path_latlon

    OSRM expects coordinates {lon},{lat} in the URL.
    Request geometries=geojson (easier than decoding polyline).
    OSRM returns GeoJSON coordinates in [lon,lat]; swap to [lat,lon] for Folium/Leaflet.
    """
    coords = f"{p_lng},{p_lat};{d_lng},{d_lat}"
    url = f"{server}/route/v1/{profile}/{coords}"
    params = {"geometries": "geojson", "overview": "full"}
    headers = {"User-Agent": "streamlit-uber-osrm-demo"}
    resp = requests.get(url, params=params, headers=headers, timeout=20)

    if resp.status_code == 429:
        raise RuntimeError("OSRM rate limit (429). Please slow down or cache more.")
    resp.raise_for_status()

    data = resp.json()
    # OSRM response format and options documented in Project OSRM's API docs. [1](https://www.freeonlinecalc.com/air-quality-index-aqi-calculation-review-and-formulas.html)
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(f"Invalid OSRM response: {data}")

    route = data["routes"][0]
    dist_km = float(route["distance"]) / 1000.0
    dur_min = float(route["duration"]) / 60.0

    coords_lonlat = route["geometry"]["coordinates"]          # [lon, lat]
    coords_latlon = [[c[1], c[0]] for c in coords_lonlat]     # swap -> [lat, lon]
    return dist_km, dur_min, coords_latlon

def local_fare_estimate(distance_km, passengers=1):
    """Simple fallback fare: base + per km + small add-on per extra passenger."""
    base = 3.0
    per_km = 1.8
    pax_fee = max(0, passengers-1) * 0.5
    return round(base + per_km*max(distance_km, 0) + pax_fee, 2)

def make_payload(pickup, dropoff, date, t, passengers):
    dt_local = datetime.combine(date, t)
    return {
        "pickup_datetime": dt_local.strftime("%Y-%m-%d %H:%M:%S"),
        "pickup_longitude": float(pickup["lng"]),
        "pickup_latitude": float(pickup["lat"]),
        "dropoff_longitude": float(dropoff["lng"]),
        "dropoff_latitude": float(dropoff["lat"]),
        "passenger_count": int(passengers),
    }

def call_fare_api(url, params):
    headers = {"Accept": "application/json"}
    resp = requests.get(url, params=params, headers=headers, timeout=20)
    if resp.status_code == 429:
        raise RuntimeError("Fare API returned 429 (Too Many Requests). Try later.")
    resp.raise_for_status()
    return resp.json()

# =========================
# PREDICTION / DISPLAY
# =========================

footer { visibility: hidden; }                                            /* default footer */
</style>
""", unsafe_allow_html=True)

st.markdown('<h2>🚕 NY Taxi App Routing</h2>', unsafe_allow_html=True)
