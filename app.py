
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
st.set_page_config(page_title="Uber-like Taxi App (OSRM)", page_icon="🚕", layout="wide")
st.markdown("""
<style>
.big-title {font-size:2.0rem;font-weight:800;margin-bottom:0.2rem}
.subtle {color:#6b7280}
.stButton>button {height:2.8rem;font-size:1rem;border-radius:10px}
.metric-row {display:flex;gap:1rem}
</style>
""", unsafe_allow_html=True)
st.markdown('<div class="big-title">🚕 Uber-like — OSRM Routing</div>', unsafe_allow_html=True)
st.markdown('<div class="subtle">Type coordinates or click the map. The nearest marker (pickup/dropoff) moves to your click.</div>', unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)

# =========================
# CONSTANTS (fixed OSRM profile & endpoints)
# =========================
OSRM_SERVER = "https://router.project-osrm.org"  # demo server (for testing)
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
    st.markdown("### 🗺️ Interactive map (OSRM)")
    center_lat = (st.session_state.pickup["lat"] + st.session_state.dropoff["lat"]) / 2
    center_lng = (st.session_state.pickup["lng"] + st.session_state.dropoff["lng"]) / 2

    # Pretty non-black basemap (choose one)
    # m = folium.Map(location=[center_lat, center_lng], zoom_start=13, tiles="CartoDB Positron")  # clean light
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

    # Render + capture clicks
    map_data = st_folium(m, height=540, width=820, key="uber_map_nyc", returned_objects=[])

    # Click handler: move the nearest marker (pickup or dropoff) to the clicked point
    if map_data and ("last_clicked" in map_data) and map_data["last_clicked"]:
        click_lat = float(map_data["last_clicked"]["lat"])
        click_lng = float(map_data["last_clicked"]["lng"])
        last = st.session_state.last_click
        if last is None or (abs(last[0]-click_lat) > 1e-10 or abs(last[1]-click_lng) > 1e-10):
            st.session_state.last_click = (click_lat, click_lng)
            # Compute distances to each marker (in degrees approximate; fine for choosing nearest)
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

    - OSRM expects coordinates {lon},{lat} in the URL
    - Request geometries=geojson (easier than decoding polyline)
    - OSRM returns GeoJSON coordinates in [lon,lat]; for Folium/Leaflet we swap to [lat,lon]
    """
    coords = f"{p_lng},{p_lat};{d_lng},{d_lat}"
    url = f"{server}/route/v1/{profile}/{coords}"
    params = {
        "geometries": "geojson",
        "overview": "full"
    }
    headers = {"User-Agent": "streamlit-uber-osrm-demo"}
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
if predict_now:
    # validations
    errs = []
    for name, pt in [("Pickup", st.session_state.pickup), ("Dropoff", st.session_state.dropoff)]:
        if not (-90 <= pt["lat"] <= 90 and -180 <= pt["lng"] <= 180):
            errs.append(f"{name}: coordinates out of bounds.")
    if passenger_count < 1:
        errs.append("Passengers must be ≥ 1.")

    if errs:
        for e in errs: st.error(e)
    else:
        # OSRM route
        with st.spinner("Routing via OSRM…"):
            try:
                dist_km, dur_min, path_latlon = call_osrm_route(
                    OSRM_SERVER, PROFILE,
                    st.session_state.pickup["lat"], st.session_state.pickup["lng"],
                    st.session_state.dropoff["lat"], st.session_state.dropoff["lng"]
                )
            except Exception as e:
                st.error(f"OSRM error: {e}")
                # Fallback straight-line approx if OSRM fails
                dist_km = math.dist(
                    (st.session_state.pickup["lat"], st.session_state.pickup["lng"]),
                    (st.session_state.dropoff["lat"], st.session_state.dropoff["lng"])
                ) * 111  # rough lat/lon -> km
                dur_min = dist_km / (22/60)  # ~22 km/h
                path_latlon = [
                    [st.session_state.pickup["lat"], st.session_state.pickup["lng"]],
                    [st.session_state.dropoff["lat"], st.session_state.dropoff["lng"]],
                ]

        # Metrics
        local_est = local_fare_estimate(dist_km, passengers=passenger_count)
        st.markdown("### 📊 Trip details")
        st.markdown('<div class="metric-row">', unsafe_allow_html=True)
        c_m1, c_m2, c_m3 = st.columns(3)
        c_m1.metric("Distance (OSRM)", f"{dist_km:.2f} km")
        c_m2.metric("Duration (OSRM)", f"{int(dur_min)} min")
        c_m3.metric("Local estimate", f"${local_est:.2f}")
        st.markdown('</div>', unsafe_allow_html=True)

        # Route map (WOW effect)
        m2 = folium.Map(location=path_latlon[0], zoom_start=13, tiles="CartoDB positron")
        folium.Marker(
            [st.session_state.pickup["lat"], st.session_state.pickup["lng"]],
            popup="Pickup",
            icon=folium.Icon(color="green", icon="play")
        ).add_to(m2)
        folium.Marker(
            [st.session_state.dropoff["lat"], st.session_state.dropoff["lng"]],
            popup="Dropoff",
            icon=folium.Icon(color="red", icon="flag")
        ).add_to(m2)
        folium.PolyLine(
            locations=path_latlon,
            color="#2A9D8F", weight=6, opacity=0.95
        ).add_to(m2)
        try:
            m2.fit_bounds(path_latlon)
        except Exception:
            pass
        st_folium(m2, height=540, width=820, key="uber_map_osrm_result", returned_objects=[])

        # Fare API
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
                with st.expander("📦 Request details"):
                    st.json({"endpoint": fare_api_url, "params": payload})
                with st.expander("📬 Raw API response"):
                    st.json(result)
            except Exception as e:
                st.error(f"Fare API error: {e}")
                st.info(f"Local fallback fare: **${local_est:.2f}**")

st.markdown("<hr>", unsafe_allow_html=True)
st.caption("Built with Streamlit • Folium • streamlit-folium • Requests • OSRM — Real route, distance & duration.")
