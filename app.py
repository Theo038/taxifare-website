
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

st.markdown('<h2>🚕 NY Taxi App Routing</h2>', unsafe_allow_html=True)
st.markdown(
    '<div>Type address or click the map. The <b>nearest marker</b> (pickup/dropoff) moves to your click.</div>',
    unsafe_allow_html=True,
)
st.markdown("<hr>", unsafe_allow_html=True)

# =========================
# CONSTANTS (OSRM & Fare API)
# =========================
OSRM_SERVER = "https://router.project-osrm.org"          # demo server
PROFILE = "driving"                                      # fixed
DEFAULT_FARE_API = "https://taxifare.lewagon.ai/predict"

with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    fare_api_url = st.text_input("Fare prediction endpoint (GET)", value=DEFAULT_FARE_API)
    st.info("OSRM demo server is rate-limited (429 possible). Avoid spamming.")

# =========================
# SESSION STATE
# =========================
def init_state():
    # NYC defaults
    if "pickup" not in st.session_state:
        st.session_state.pickup = {"lat": 40.7580, "lng": -73.9855}   # Times Square
    if "dropoff" not in st.session_state:
        st.session_state.dropoff = {"lat": 40.7676, "lng": -73.9817}  # Central Park South
    if "last_click" not in st.session_state:
        st.session_state.last_click = None
    if "pickup_address" not in st.session_state:
        st.session_state.pickup_address = "Times Square, New York, NY"
    if "dropoff_address" not in st.session_state:
        st.session_state.dropoff_address = "Central Park South, New York, NY"

init_state()

# =========================
# GEOCODING (Nominatim)
# =========================
@st.cache_data(ttl=600, show_spinner=False)
def geocode_address(q: str, countrycodes="us"):
    """
    Geocode using Nominatim Search API (jsonv2).
    Respect usage policy: provide User-Agent, keep <=1 req/s, cache results.  (docs)  [1](https://nominatim.org/release-docs/latest/api/Search/)[2](https://operations.osmfoundation.org/policies/nominatim/)
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": q,
        "format": "jsonv2",
        "limit": 1,
        "countrycodes": countrycodes,
    }
    headers = {
        # Identify your app per policy; put a contact email/URL if you deploy publicly.
        "User-Agent": "ny-taxi-app/1.0 (contact: user@example.com)"
    }
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    if resp.status_code == 429:
        raise RuntimeError("Nominatim rate limit (429). Please slow down.")
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return None
    item = data[0]
    return {
        "lat": float(item["lat"]),
        "lng": float(item["lon"]),
        "display_name": item.get("display_name", q),
    }

# =========================
# UI CONTROLS
# =========================
left, right = st.columns([0.42, 0.58])

with left:
    st.markdown("### 🎛️ Trip parameters")
    c_dt1, c_dt2 = st.columns(2)
    trip_date = c_dt1.date_input("Date", value=datetime.now().date())
    trip_time = c_dt2.time_input("Time", value=time(12, 0))

    # --- Address inputs + Geocode buttons ---
    st.markdown("#### 📍 Pickup address")
    col_pa1, col_pa2 = st.columns([3, 1])
    st.session_state.pickup_address = col_pa1.text_input(
        "Enter pickup address",
        value=st.session_state.pickup_address,
        placeholder="e.g., 1600 Broadway, New York, NY",
    )
    if col_pa2.button("🔎 Geocode pickup"):
        try:
            res = geocode_address(st.session_state.pickup_address)
            if res is None:
                st.warning("No result for pickup address.")
            else:
                st.session_state.pickup = {"lat": res["lat"], "lng": res["lng"]}
                # overwrite normalized display name
                st.session_state.pickup_address = res["display_name"]
                st.rerun()
        except Exception as e:
            st.error(f"Pickup geocoding failed: {e}")

    st.markdown("#### 🏁 Dropoff address")
    col_da1, col_da2 = st.columns([3, 1])
    st.session_state.dropoff_address = col_da1.text_input(
        "Enter dropoff address",
        value=st.session_state.dropoff_address,
        placeholder="e.g., 10 Columbus Cir, New York, NY",
    )
    if col_da2.button("🔎 Geocode dropoff"):
        try:
            res = geocode_address(st.session_state.dropoff_address)
            if res is None:
                st.warning("No result for dropoff address.")
            else:
                st.session_state.dropoff = {"lat": res["lat"], "lng": res["lng"]}
                st.session_state.dropoff_address = res["display_name"]
                st.rerun()
        except Exception as e:
            st.error(f"Dropoff geocoding failed: {e}")

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
        st.session_state.last_click = None
        st.rerun()

with right:
    st.markdown("### 🗺️ Interactive map")
    center_lat = (st.session_state.pickup["lat"] + st.session_state.dropoff["lat"]) / 2
    center_lng = (st.session_state.pickup["lng"] + st.session_state.dropoff["lng"]) / 2

    # Light basemap (reliable alias)
    m = folium.Map(location=[center_lat, center_lng], zoom_start=13, tiles="CartoDB positron")

    # Markers with address popups
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

    # Straight line before OSRM route
    folium.PolyLine(
        locations=[
            [st.session_state.pickup["lat"], st.session_state.pickup["lng"]],
            [st.session_state.dropoff["lat"], st.session_state.dropoff["lng"]],
        ],
        color="#bbb", weight=2, opacity=0.5
    ).add_to(m)

    # Render + capture clicks (per streamlit-folium docs, use 'last_clicked')  [5](https://folium.streamlit.app/)
    map_data = st_folium(m, height=540, width=820, key="uber_map_nyc", returned_objects=[])

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
                    st.session_state.pickup_address = f"{click_lat:.6f}, {click_lng:.6f}"
                else:
                    st.session_state.dropoff = {"lat": click_lat, "lng": click_lng}
                    st.session_state.dropoff_address = f"{click_lat:.6f}, {click_lng:.6f}"
                st.rerun()

# =========================
# HELPERS & OSRM
# =========================
@st.cache_data(show_spinner=False, ttl=300)
def call_osrm_route(server, profile, p_lat, p_lng, d_lat, d_lng):
    """
    Call OSRM /route and return: distance_km, duration_min, path_latlon.

    OSRM expects {lon},{lat} in URL; we request geometries=geojson + overview=full
    and convert [lon,lat] -> [lat,lon] for Folium.  (docs)  [3](http://project-osrm.org/docs/v5.5.1/api/)[4](https://github.com/Project-OSRM/osrm-backend/blob/master/include/engine/api/route_parameters.hpp)
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
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(f"Invalid OSRM response: {data}")

    route = data["routes"][0]
    dist_km = float(route["distance"]) / 1000.0
    dur_min = float(route["duration"]) / 60.0

    coords_lonlat = route["geometry"]["coordinates"]          # [lon, lat]
    coords_latlon = [[c[1], c[0]] for c in coords_lonlat]     # swap -> [lat, lon]
    return dist_km, dur_min, coords_latlon

def local_fare_estimate(distance_km, passengers=1):
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
    errs = []
    for name, pt in [("Pickup", st.session_state.pickup), ("Dropoff", st.session_state.dropoff)]:
        if not (-90 <= pt["lat"] <= 90 and -180 <= pt["lng"] <= 180):
            errs.append(f"{name}: coordinates out of bounds.")
    if passenger_count < 1:
        errs.append("Passengers must be ≥ 1.")

    if errs:
        for e in errs:
            st.error(e)
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
                dist_km = math.dist(
                    (st.session_state.pickup["lat"], st.session_state.pickup["lng"]),
                    (st.session_state.dropoff["lat"], st.session_state.dropoff["lng"])
                ) * 111
                dur_min = dist_km / (22/60)
                path_latlon = [
                    [st.session_state.pickup["lat"], st.session_state.pickup["lng"]],
                    [st.session_state.dropoff["lat"], st.session_state.dropoff["lng"]],
                ]

        # Metrics
        local_est = local_fare_estimate(dist_km, passengers=passenger_count)
        st.markdown("### 📊 Trip details")
        c_m1, c_m2, c_m3 = st.columns(3)
        c_m1.metric("Distance (OSRM)", f"{dist_km:.2f} km")
        c_m2.metric("Duration (OSRM)", f"{int(dur_min)} min")
        c_m3.metric("Local estimate", f"${local_est:.2f}")

        # Route map
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
