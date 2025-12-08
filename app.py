
# app.py
# Streamlit NY Taxi App — Address Autocomplete + OSRM Routing
# -----------------------------------------------------------
# Features:
#   • Live address AUTOCOMPLETE (Mapbox v6 preferred, LocationIQ fallback)
#   • Map click-to-move: the NEAREST marker (pickup/dropoff) moves to your click
#   • OSRM routing (driving): real road geometry, distance & duration
#   • Clean light basemap (CartoDB positron)
#   • Hidden Streamlit toolbar/badge per styling
#
# Provider docs:
#   • Mapbox Geocoding v6 (forward, autocomplete, proximity, bbox):
#       https://docs.mapbox.com/api/search/geocoding-v6/       # ← API reference
#       https://docs.mapbox.com/playground/geocoding/          # ← Playground
#   • LocationIQ Autocomplete:
#       https://docs.locationiq.com/docs/autocomplete          # ← Overview/usage
#       https://docs.locationiq.com/reference/autocomplete-2   # ← API reference
#   • OSRM Route API (geometries=geojson, overview=full):
#       http://project-osrm.org/docs/v5.5.1/api/               # ← API docs

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
st.set_page_config(page_title="NY Taxi App — Autocomplete + OSRM", page_icon="🚕", layout="wide")

# Hide Streamlit toolbar / badge / footer
st.markdown(
    """
    <style>
    div[data-testid="st    footer { visibility: hidden; }    div[data-testid="stToolbar"] { visibility: hidden; height: 0px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<h2>🚕 NY Taxi App — Address Autocomplete + OSRM Routing</h2>', unsafe_allow_html=True)
st.markdown(
    '<div>Type addresses or click the map. The <b>nearest marker</b> (pickup/dropoff) moves to your click.</div>',
    unsafe_allow_html=True,
)
st.markdown("<hr>", unsafe_allow_html=True)

# =========================
# CONSTANTS & TOKENS
# =========================
OSRM_SERVER = "https://router.project-osrm.org"        # demo server
PROFILE = "driving"                                     # fixed
DEFAULT_FARE_API = "https://taxifare.lewagon.ai/predict"
NYC_VIEWBOX = (-74.259, 40.477, -73.700, 40.917)        # lon/lat bbox NYC
NYC_CENTER = (-73.9855, 40.7580)                        # (lon, lat) Times Sq proximity

# Autocomplete providers (set tokens via environment)
MAPBOX_ACCESS_TOKEN = os.getenv("MAPBOX_ACCESS_TOKEN")          # preferred for autocomplete (v6)
LOCATIONIQ_TOKEN = os.getenv("LOCATIONIQ_TOKEN")                # fallback autocomplete

with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    fare_api_url = st.text_input("Fare prediction endpoint (GET)", value=DEFAULT_FARE_API)
    if MAPBOX_ACCESS_TOKEN:
        st.success("Mapbox token detected — live autocomplete enabled.")
    elif LOCATIONIQ_TOKEN:
        st.success("LocationIQ token detected — live autocomplete enabled.")
    else:
        st.warning("No autocomplete token detected. Set MAPBOX_ACCESS_TOKEN or LOCATIONIQ_TOKEN in environment.")

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
    if "pickup_last_autocomplete" not in st.session_state:
        st.session_state.pickup_last_autocomplete = 0.0
    if "dropoff_last_autocomplete" not in st.session_state:
        st.session_state.dropoff_last_autocomplete = 0.0

init_state()

# =========================
# PROVIDERS — Autocomplete (Mapbox, LocationIQ)
# =========================
def autocomplete_mapbox(q: str, limit=6, bbox=NYC_VIEWBOX, proximity=NYC_CENTER):
    """Mapbox Geocoding v6 forward with autocomplete (docs: geocoding v6)."""
    if not MAPBOX_ACCESS_TOKEN:
        return []
    url = "https://api.mapbox.com/search/geocode/v6/forward"
    params = {
        "q": q,
        "limit": limit,
        "autocomplete": "true",
        "country": "US",
        "bbox": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
        "proximity": f"{proximity[0]},{proximity[1]}",
        "access_token": MAPBOX_ACCESS_TOKEN,
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    out = []
    for feat in data.get("features", []):
        coords = feat.get("geometry", {}).get("coordinates")
        if not coords or len(coords) < 2:
            continue
        lon, lat = coords[0], coords[1]
        props = feat.get("properties", {}) or {}
        label = props.get("full_address") or props.get("name") or feat.get("place_name") or q
        out.append({"label": label, "lat": float(lat), "lng": float(lon)})
    return out

def autocomplete_locationiq(q: str, limit=6, countrycodes="us", viewbox=NYC_VIEWBOX, bounded=1):
    """LocationIQ Autocomplete endpoint (docs)."""
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
        lat = float(item.get("lat")); lng = float(item.get("lon"))
        out.append({"label": label, "lat": lat, "lng": lng})
    return out

def get_suggestions(q: str, is_pickup: bool):
    """
    Fetch suggestions using available provider (Mapbox preferred, else LocationIQ).
    Throttle calls to ~0.6s between keystrokes.
    """
    now = time.time()
    last_key = "pickup_last_autocomplete" if is_pickup else "dropoff_last_autocomplete"
    if now - st.session_state[last_key] < 0.6:
        return
    st.session_state[last_key] = now

    suggestions = []
    if MAPBOX_ACCESS_TOKEN:
        try:
            suggestions = autocomplete_mapbox(q)
        except Exception as e:
            st.warning(f"Autocomplete error (Mapbox): {e}")
    elif LOCATIONIQ_TOKEN:
        try:
            suggestions = autocomplete_locationiq(q)
        except Exception as e:
            st.warning(f"Autocomplete error (LocationIQ): {e}")
    else:
        st.info("No autocomplete provider configured. Set MAPBOX_ACCESS_TOKEN or LOCATIONIQ_TOKEN.")

    if is_pickup:
        st.session_state.pickup_suggestions = suggestions
    else:
        st.session_state.dropoff_suggestions = suggestions

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
    if len(st.session_state.pickup_query.strip()) >= 3:
        get_suggestions(st.session_state.pickup_query.strip(), is_pickup=True)

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
    if len(st.session_state.dropoff_query.strip()) >= 3:
        get_suggestions(st.session_state.dropoff_query.strip(), is_pickup=False)

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
    folium.Marker(
        [st.session_state.dropoff["lat"], st.session_state.dropoff["lng"]],
        popup=f"Dropoff:<br>{st.session_state.dropoff_address}",
        icon=folium.Icon(color="red", icon="flag")
    ).add_to(m)

    folium.PolyLine(
        locations=[
            [st.session_state.pickup["lat"], st.session_state.pickup["lng"]],
            [st.session_state.dropoff["lat"], st.session_state.dropoff["lng"]],
        ],
        color="#bbb", weight=2, opacity=0.5
    ).add_to(m)

    map_data = st_folium(m, height=540, width=820, key="uber_map_nyc", returned_objects=[])

    # Click handler: move the nearest marker
    click = (map_data or {}).get("last_clicked")
    if click:
        try:
            click_lat = float(click.get("lat"))
            click_lng = float(click.get("lng"))
        except (TypeError, ValueError):
            click_lat = click_lng = None

        if click_lat is not None and click_lng is not None:
            last = st.session_state.last_click
            if last is None or (abs(last[0] - click_lat) > 1e-10 or abs(last[1] - click_lng) > 1e-10):
                st.session_state.last_click = (click_lat, click_lng)
                d_pick = math.hypot(click_lat - st.session_state.pickup["lat"], click_lng - st.session_state.pickup["lng"])
                d_drop = math.hypot(click_lat - st.session_state.dropoff["lat"], click_lng - st.session_state.dropoff["lng"])
                if d_pick <= d_drop:
                    st.session_state.pickup = {"lat": click_lat, "lng": click_lng}
                    st.session_state.pickup_address = f"{click_lat:.6f}, {click_lng:.6f}"
                    st.session_state.pickup_query = st.session_state.pickup_address
                else:
                    st.session_state.dropoff = {"lat": click_lat, "lng": click_lng}
                    st.session_state.dropoff_address = f"{click_lat:.6f}, {click_lng:.6f}"
                    st.session_state.dropoff_query = st.session_state.dropoff_address
                st.rerun()

# =========================
# OSRM ROUTING
# =========================
@st.cache_data(show_spinner=False, ttl=300)
def call_osrm_route(server, profile, p_lat, p_lng, d_lat, d_lng):
    """
    Call OSRM /route and return: distance_km, duration_min, path_latlon.
    (Docs: OSRM HTTP API — geometries=geojson, overview=full)
    """
    coords = f"{p_lng},{p_lat};{d_lng},{d_lat}"
    url = f"{server}/route/v1/{profile}/{coords}"
    params = {"geometries": "geojson", "overview": "full"}
    headers = {"User-Agent": "ny-taxi-app/1.0"}
    resp = requests.get(url, params=params, headers=headers, timeout=20)
    if resp.status_code == 429:
        raise RuntimeError("OSRM rate limit (429). Please slow down or cache more.")
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(f"Invalid OSRM response: {data}")
    route = data["routes"][0]
    dist_km = float(route["distance"]) / 1000.0
    dur_min = float(route["duration"]) / 60.0
    coords_lonlat = route["geometry"]["coordinates"]          # [lon, lat]
    coords_latlon = [[c[1], c[0]] for c in coords_lonlat]     # swap -> [lat, lon]
    return dist_km, dur_min, coords_latlon

def local_fare_estimate(distance_km, passengers=1):
    base = 3.0; per_km = 1.8; pax_fee = max(0, passengers-1) * 0.5
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
if 'predict_now' not in locals():  # ensure symbol exists
    predict_now = False

if predict_now:
    errs = []
    for name, pt in [("Pickup", st.session_state.pickup), ("Dropoff", st.session_state.dropoff)]:
        if not (-90 <= pt["lat"] <= 90 and -180 <= pt["lng"] <= 180):
            errs.append(f"{name}: coordinates out of bounds.")
    if passenger_count < 1:
        errs.append("Passengers must be ≥ 1.")
    if errs:
        for e in errs: st.error(e)
    else:
        with st.spinner("Routing via OSRM…"):
            try:
                dist_km, dur_min, path_latlon = call_osrm_route(
                    OSRM_SERVER, PROFILE,
                    st.session_state.pickup["lat"], st.session_state.pickup["lng"],
                    st.session_state.dropoff["lat"], st.session_state.dropoff["lng"]
                )
            except Exception as e:
                st.error(f"OSRM error: {e}")
                dist_km = math.dist(
                    (st.session_state.pickup["lat"], st.session_state.pickup["lng"]),
                    (st.session_state.dropoff["lat"], st.session_state.dropoff["lng"])
                ) * 111
                dur_min = dist_km / (22/60)
                path_latlon = [
                    [st.session_state.pickup["lat"], st.session_state.pickup["lng"]],
                    [st.session_state.dropoff["lat"], st.session_state.dropoff["lng"]],
                ]

        local_est = local_fare_estimate(dist_km, passengers=passenger_count)
        st.markdown("### 📊 Trip details")
        c_m1, c_m2, c_m3 = st.columns(3)
        c_m1.metric("Distance (OSRM)", f"{dist_km:.2f} km")
        c_m2.metric("Duration (OSRM)", f"{int(dur_min)} min")
        c_m3.metric("Local estimate", f"${local_est:.2f}")

        m2 = folium.Map(location=path_latlon[0], zoom_start=13, tiles="CartoDB positron")
        folium.Marker(
            [st.session_state.pickup["lat"], st.session_state.pickup["lng"]],
            popup=f"Pickup:<br>{st.session_state.pickup_address}",
            icon=folium.Icon(color="green", icon="play")
        ).add_to(m2)
        folium.Marker(
            [st.session_state.dropoff["lat"], st.session_state.dropoff["lng"]],
            popup=f"Dropoff:<br>{st.session_state.dropoff_address}",
            icon=folium.Icon(color="red", icon="flag")
        ).add_to(m2)
        folium.PolyLine(locations=path_latlon, color="#2A9D8F", weight=6, opacity=0.95).add_to(m2)
        try: m2.fit_bounds(path_latlon)
        except Exception: pass
        st_folium(m2, height=540, width=820, key="uber_map_osrm_result", returned_objects=[])

        with st.spinner("Calling fare API…"):
            try:
                payload = make_payload(st.session_state.pickup, st.session_state.dropoff, trip_date, trip_time, passenger_count)
                result = call_fare_api(fare_api_url, payload)
                fare = result.get("fare") or result.get("prediction") or result.get("y_pred")
                if fare is not None:
                    st.success("Prediction received (API)")
                    st.metric("💵 Estimated fare (API)", f"${float(fare):.2f}")
                else:
                    st.warning("API returned JSON but no 'fare' key — showing local estimate.")
                with st.expander("📦 Request details"): st.json({"endpoint": fare_api_url, "params": payload})
                with st.expander("📬 Raw API response"): st.json(result)
            except Exception as e:
                st.error(f"Fare API error: {e}")
                st.info(f"Local fallback fare: **${local_est:.2f}**")
