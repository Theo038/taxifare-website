
import os
import requests
import streamlit as st
from datetime import datetime, time
import folium
from streamlit_folium import st_folium

# ------------------------------------------------------------
# PAGE CONFIG + TITLE
# ------------------------------------------------------------
st.set_page_config(page_title="Taxi Fare Front (WOW)", page_icon="🚕", layout="centered")

st.markdown(
    """
    <style>
    .wow-header {
        font-size: 2.2rem; font-weight: 700;
        background: linear-gradient(90deg, #FFB703, #FB8500);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin-bottom: 0.3rem;
    }
    .subtle {
        color: #60656c;
    }
    </style>
    """,
    unsafe_allow_html=True
)
st.markdown('<div class="wow-header">🚕 Taxi Fare Prediction – WOW Edition</div>', unsafe_allow_html=True)
st.markdown('<div class="subtle">Click the map or type coordinates—then hit <b>Predict fare</b>.</div>', unsafe_allow_html=True)
st.divider()

# ------------------------------------------------------------
# API CONFIG (you can replace with your own endpoint)
# ------------------------------------------------------------
DEFAULT_API_URL = "https://taxifare.lewagon.ai/predict"
api_url = st.text_input(
    "Prediction API endpoint",
    value=DEFAULT_API_URL,
    help="Change this to your own API if needed (must accept GET with query params).",
)

if api_url == DEFAULT_API_URL:
    st.info("Using the Le Wagon demo API. Set your own endpoint above to call a custom model.")

# ------------------------------------------------------------
# SESSION STATE (persists while user interacts)
# ------------------------------------------------------------
def init_state():
    if "pickup" not in st.session_state:
        st.session_state.pickup = {"lat": 40.748817, "lng": -73.985428}  # default: Midtown
    if "dropoff" not in st.session_state:
        st.session_state.dropoff = {"lat": 40.758896, "lng": -73.985428}  # nearby
    if "map_mode" not in st.session_state:
        st.session_state.map_mode = "Set Pickup"

init_state()

# ------------------------------------------------------------
# INPUTS (date/time & coords)
# ------------------------------------------------------------
st.subheader("Trip parameters")
col_dt1, col_dt2 = st.columns(2)
trip_date = col_dt1.date_input("Date", value=datetime.now().date())
trip_time = col_dt2.time_input("Time", value=time(12, 0))

col_pick, col_drop = st.columns(2)
with col_pick:
    st.caption("Pickup (type or click on map)")
    pickup_longitude = st.number_input("Pickup longitude", value=float(st.session_state.pickup["lng"]), format="%.6f")
    pickup_latitude  = st.number_input("Pickup latitude",  value=float(st.session_state.pickup["lat"]), format="%.6f")
    if st.button("Update map from pickup inputs", use_container_width=True):
        st.session_state.pickup = {"lat": float(pickup_latitude), "lng": float(pickup_longitude)}

with col_drop:
    st.caption("Dropoff (type or click on map)")
    dropoff_longitude = st.number_input("Dropoff longitude", value=float(st.session_state.dropoff["lng"]), format="%.6f")
    dropoff_latitude  = st.number_input("Dropoff latitude",  value=float(st.session_state.dropoff["lat"]), format="%.6f")
    if st.button("Update map from dropoff inputs", use_container_width=True):
        st.session_state.dropoff = {"lat": float(dropoff_latitude), "lng": float(dropoff_longitude)}

col_pass_1, col_pass_2 = st.columns([1, 1])
with col_pass_1:
    passenger_count = st.number_input("Passenger count", min_value=1, max_value=8, value=1, step=1)
with col_pass_2:
    st.session_state.map_mode = st.radio(
        "Map click mode",
        ["Set Pickup", "Set Dropoff"],
        horizontal=True
    )

# ------------------------------------------------------------
# FOLIUM MAP (click-to-set)
# ------------------------------------------------------------
def make_map(center_lat, center_lng, pickup=None, dropoff=None):
    m = folium.Map(location=[center_lat, center_lng], zoom_start=13, tiles="CartoDB Positron")
    # Pickup marker
    if pickup:
        folium.Marker(
            location=[pickup["lat"], pickup["lng"]],
            popup="Pickup",
            icon=folium.Icon(color="green", icon="play")
        ).add_to(m)
    # Dropoff marker
    if dropoff:
        folium.Marker(
            location=[dropoff["lat"], dropoff["lng"]],
            popup="Dropoff",
            icon=folium.Icon(color="red", icon="flag")
        ).add_to(m)
    # Line between points
    if pickup and dropoff:
        folium.PolyLine(
            locations=[[pickup["lat"], pickup["lng"]], [dropoff["lat"], dropoff["lng"]]],
            color="#3A86FF", weight=4, opacity=0.7
        ).add_to(m)
    return m

# Center map roughly between pickup and dropoff
center_lat = (st.session_state.pickup["lat"] + st.session_state.dropoff["lat"]) / 2
center_lng = (st.session_state.pickup["lng"] + st.session_state.dropoff["lng"]) / 2

st.subheader("Interactive map")
st.caption("Click on map to set the coordinate of the selected mode (Pickup or Dropoff).")
m = make_map(center_lat, center_lng, st.session_state.pickup, st.session_state.dropoff)
map_data = st_folium(m, height=520, width=720, key="map")

# Handle clicks: streamlit-folium returns dict with keys like 'last_clicked'
if map_data and ("last_clicked" in map_data) and map_data["last_clicked"]:
    lat = float(map_data["last_clicked"]["lat"])
    lng = float(map_data["last_clicked"]["lng"])
    if st.session_state.map_mode == "Set Pickup":
        st.session_state.pickup = {"lat": lat, "lng": lng}
    else:
        st.session_state.dropoff = {"lat": lat, "lng": lng}
    # Sync the number inputs by rerunning (Streamlit auto-runs; values are read above from session_state)

st.divider()

# ------------------------------------------------------------
# PAYLOAD + API CALL
# ------------------------------------------------------------
def make_payload() -> dict:
    """
    Create the query dict expected by typical /predict APIs:
    pickup_datetime, pickup_longitude, pickup_latitude,
    dropoff_longitude, dropoff_latitude, passenger_count
    """
    dt_local = datetime.combine(trip_date, trip_time)
    pickup_datetime = dt_local.strftime("%Y-%m-%d %H:%M:%S")  # "YYYY-MM-DD HH:MM:SS"

    payload = {
        "pickup_datetime":   pickup_datetime,
        "pickup_longitude":  float(st.session_state.pickup["lng"]),
        "pickup_latitude":   float(st.session_state.pickup["lat"]),
        "dropoff_longitude": float(st.session_state.dropoff["lng"]),
        "dropoff_latitude":  float(st.session_state.dropoff["lat"]),
        "passenger_count":   int(passenger_count),
    }
    return payload

def call_api(url: str, params: dict) -> dict:
    """
    Call the prediction API and return JSON.
    Expects { "fare": <float> } or similar.
    """
    headers = {"Accept": "application/json"}
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    if resp.status_code == 200:
        try:
            return resp.json()
        except Exception as e:
            raise RuntimeError(f"Invalid JSON in response: {e}") from e
    elif resp.status_code == 404:
        raise RuntimeError("Endpoint not found (404). Check your API URL.")
    elif resp.status_code == 422:
        raise RuntimeError("Validation error (422). Check your parameter ranges/format.")
    elif resp.status_code == 429:
        raise RuntimeError("Too Many Requests (429). Please slow down or try later.")
    else:
        raise RuntimeError(f"API error {resp.status_code}: {resp.text}")

# ------------------------------------------------------------
# ACTION: PREDICT
# ------------------------------------------------------------
st.subheader("Prediction")
predict_col, reset_col = st.columns([2,1])
with predict_col:
    if st.button("Predict fare", type="primary", use_container_width=True):
        # Basic input sanity checks
        errors = []
        if passenger_count < 1:
            errors.append("Passenger count must be ≥ 1.")
        for (name, pt) in [("Pickup", st.session_state.pickup), ("Dropoff", st.session_state.dropoff)]:
            if not (-180.0 <= pt["lng"] <= 180.0 and -90.0 <= pt["lat"] <= 90.0):
                errors.append(f"{name} coordinates look out of bounds.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            with st.spinner("Calling prediction API…"):
                try:
                    payload = make_payload()
                    result = call_api(api_url, payload)
                    fare = result.get("fare") or result.get("prediction") or result.get("pred") or result.get("y_pred")

                    if fare is None:
                        st.warning(f"API returned JSON but no 'fare' key was found:\n```\n{result}\n```")
                    else:
                        st.success("Prediction received!")
                        st.metric("💵 Estimated fare", f"${float(fare):.2f}")
                        with st.expander("Request details"):
                            st.json({"endpoint": api_url, "params": payload})
                        with st.expander("Raw API response"):
                            st.json(result)
                except Exception as e:
                    st.error(f"Prediction failed: {e}")

with reset_col:
    if st.button("Reset points", use_container_width=True):
        st.session_state.pickup = {"lat": 40.748817, "lng": -73.985428}
        st.session_state.dropoff = {"lat": 40.758896, "lng": -73.985428}
        st.experimental_rerun()

# ------------------------------------------------------------
# FOOTER
# ------------------------------------------------------------
st.caption("Built with Streamlit • Folium • streamlit-folium • requests. Click the map to set pickup/dropoff.")
