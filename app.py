
# app_osrm.py
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
.big-title {font-size:2.1rem;font-weight:800;margin-bottom:0.2rem}
.subtle {color:#6b7280}
.stButton>button {height:2.8rem;font-size:1rem;border-radius:10px}
.metric-row {display:flex;gap:1rem}
</style>
""", unsafe_allow_html=True)
st.markdown('<div class="big-title">🚕 Uber-like — OSRM Routing</div>', unsafe_allow_html=True)
st.markdown('<div class="subtle">Clique sur la carte (Pickup / Dropoff), puis « Demander un chauffeur ».</div>', unsafe_allow_html=True)
st.markdown("<hr>", unsafe_allow_html=True)

# =========================
# CONFIG OSRM + API tarif
# =========================
OSRM_SERVER = st.sidebar.text_input(
    "OSRM server (demo par défaut)",
    value="https://router.project-osrm.org",
    help="Pour la prod, utilise ton propre serveur OSRM (ou un service dédié)."
)
PROFILE = st.sidebar.selectbox("Profil OSRM", ["driving", "foot", "bike"], index=0)
DEFAULT_API_URL = "https://taxifare.lewagon.ai/predict"
api_url = st.sidebar.text_input("Endpoint prédiction (GET)", value=DEFAULT_API_URL)

st.sidebar.info("Le serveur démo OSRM est limité et peut renvoyer des 429. Évite de spammer.")

# =========================
# SESSION STATE
# =========================
def init_state():
    # Par défaut: centre-ville (ex: Grenoble)
    if "pickup" not in st.session_state:
        st.session_state.pickup = {"lat": 45.188529, "lng": 5.724524}
    if "dropoff" not in st.session_state:
        st.session_state.dropoff = {"lat": 45.204994, "lng": 5.726457}
    if "map_mode" not in st.session_state:
        st.session_state.map_mode = "Pickup"
    if "last_click" not in st.session_state:
        st.session_state.last_click = None

init_state()

# =========================
# UI CONTROLS
# =========================
left, right = st.columns([0.38, 0.62])

with left:
    st.markdown("### 🎛️ Paramètres du trajet")
    c_dt1, c_dt2 = st.columns(2)
    trip_date = c_dt1.date_input("Date", value=datetime.now().date())
    trip_time = c_dt2.time_input("Heure", value=time(12, 0))

    st.session_state.map_mode = st.radio("Mode clic carte", ["Pickup", "Dropoff"], horizontal=True)

    st.markdown("#### 📍 Pickup")
    p1, p2 = st.columns(2)
    pickup_lat = p1.number_input("Latitude pickup", value=float(st.session_state.pickup["lat"]), format="%.6f")
    pickup_lng = p2.number_input("Longitude pickup", value=float(st.session_state.pickup["lng"]), format="%.6f")
    if st.button("🔄 Mettre la carte à jour (pickup)"):
        st.session_state.pickup = {"lat": float(pickup_lat), "lng": float(pickup_lng)}

    st.markdown("#### 🏁 Dropoff")
    d1, d2 = st.columns(2)
    dropoff_lat = d1.number_input("Latitude dropoff", value=float(st.session_state.dropoff["lat"]), format="%.6f")
    dropoff_lng = d2.number_input("Longitude dropoff", value=float(st.session_state.dropoff["lng"]), format="%.6f")
    if st.button("🔄 Mettre la carte à jour (dropoff)"):
        st.session_state.dropoff = {"lat": float(dropoff_lat), "lng": float(dropoff_lng)}

    passenger_count = st.slider("👥 Passagers", min_value=1, max_value=6, value=1)

    st.markdown("<hr>", unsafe_allow_html=True)
    cta1, cta2 = st.columns([2, 1])
    with cta1:
        predict_now = st.button("🚗 Demander un chauffeur", type="primary")
    with cta2:
        reset = st.button("🧹 Reset points")
    if reset:
        st.session_state.pickup = {"lat": 45.188529, "lng": 5.724524}
        st.session_state.dropoff = {"lat": 45.204994, "lng": 5.726457}
        st.session_state.last_click = None
        st.experimental_rerun()

with right:
    st.markdown("### 🗺️ Carte interactive (OSRM)")
    center_lat = (st.session_state.pickup["lat"] + st.session_state.dropoff["lat"]) / 2
    center_lng = (st.session_state.pickup["lng"] + st.session_state.dropoff["lng"]) / 2

    m = folium.Map(location=[center_lat, center_lng], zoom_start=13, tiles="CartoDB Positron")

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

    # Affichage provisoire de ligne droite (remplacée plus bas par l'itinéraire OSRM)
    folium.PolyLine(
        locations=[
            [st.session_state.pickup["lat"], st.session_state.pickup["lng"]],
            [st.session_state.dropoff["lat"], st.session_state.dropoff["lng"]],
        ],
        color="#bbb", weight=2, opacity=0.5
    ).add_to(m)

    map_data = st_folium(m, height=520, width=800, key="uber_map_osrm", returned_objects=[])

    if map_data and ("last_clicked" in map_data) and map_data["last_clicked"]:
        click_lat = float(map_data["last_clicked"]["lat"])
        click_lng = float(map_data["last_clicked"]["lng"])
        last = st.session_state.last_click
        if last is None or (abs(last[0]-click_lat) > 1e-10 or abs(last[1]-click_lng) > 1e-10):
            st.session_state.last_click = (click_lat, click_lng)
            if st.session_state.map_mode == "Pickup":
                st.session_state.pickup = {"lat": click_lat, "lng": click_lng}
            else:
                st.session_state.dropoff = {"lat": click_lat, "lng": click_lng}
            st.experimental_rerun()

# =========================
# OUTILS & OSRM
# =========================
@st.cache_data(show_spinner=False, ttl=300)
def call_osrm_route(server, profile, p_lat, p_lng, d_lat, d_lng):
    """
    Appelle OSRM /route, retourne distance (km), durée (min) et GeoJSON (liste de [lat, lng]).
    """
    # OSRM attend des coords en [lon,lat]; on construit l’URL officielle.
    coords = f"{p_lng},{p_lat};{d_lng},{d_lat}"
    url = f"{server}/route/v1/{profile}/{coords}"
    params = {
        "geometries": "geojson",    # GeoJSON pour éviter le décodage polyline
        "overview": "full"          # géométrie détaillée
        # "steps": "false",          # (optionnel) étapes de navigation
    }
    headers = {"User-Agent": "streamlit-uber-osrm-demo"}  # bon usage: User-Agent
    resp = requests.get(url, params=params, headers=headers, timeout=20)

    if resp.status_code == 429:
        raise RuntimeError("OSRM a renvoyé 429 (rate limit). Réduis la fréquence des requêtes.")

    if resp.status_code != 200:
        raise RuntimeError(f"Erreur OSRM {resp.status_code}: {resp.text}")

    data = resp.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RuntimeError(f"Réponse OSRM non valide: {data}")

    route = data["routes"][0]
    dist_km = float(route["distance"]) / 1000.0
    dur_min = float(route["duration"]) / 60.0

    # OSRM GeoJSON = [lon, lat]; Folium PolyLine attend [lat, lon]
    coords_lonlat = route["geometry"]["coordinates"]
    coords_latlon = [[c[1], c[0]] for c in coords_lonlat]

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
    if resp.status_code == 200:
        return resp.json()
    elif resp.status_code == 429:
        raise RuntimeError("Trop de requêtes (429). Essaie plus tard.")
    else:
        raise RuntimeError(f"Erreur API {resp.status_code}: {resp.text}")

# =========================
# PRÉDICTION / AFFICHAGE
# =========================
if predict_now:
    # validations
    errs = []
    for name, pt in [("Pickup", st.session_state.pickup), ("Dropoff", st.session_state.dropoff)]:
        if not (-90 <= pt["lat"] <= 90 and -180 <= pt["lng"] <= 180):
            errs.append(f"{name}: coordonnées hors bornes.")
    if passenger_count < 1:
        errs.append("Passagers: au moins 1.")
    if errs:
        for e in errs: st.error(e)
    else:
        # OSRM route
        with st.spinner("Calcul d’itinéraire (OSRM)…"):
            try:
                dist_km, dur_min, path_latlon = call_osrm_route(
                    OSRM_SERVER, PROFILE,
                    st.session_state.pickup["lat"], st.session_state.pickup["lng"],
                    st.session_state.dropoff["lat"], st.session_state.dropoff["lng"]
                )
            except Exception as e:
                st.error(f"Échec OSRM: {e}")
                dist_km = math.dist(
                    (st.session_state.pickup["lat"], st.session_state.pickup["lng"]),
                    (st.session_state.dropoff["lat"], st.session_state.dropoff["lng"])
                ) * 111  # approx. km en lat/lon (fallback)
                dur_min = dist_km / (22/60)  # 22 km/h
                path_latlon = [
                    [st.session_state.pickup["lat"], st.session_state.pickup["lng"]],
                    [st.session_state.dropoff["lat"], st.session_state.dropoff["lng"]],
                ]

        # Affiche métriques
        local_est = local_fare_estimate(dist_km, passengers=passenger_count)
        st.markdown("### 📊 Détails trajet")
        st.markdown('<div class="metric-row">', unsafe_allow_html=True)
        c_m1, c_m2, c_m3 = st.columns(3)
        c_m1.metric("Distance (OSRM)", f"{dist_km:.2f} km")
        c_m2.metric("Durée (OSRM)", f"{int(dur_min)} min")
        c_m3.metric("Estimation locale", f"${local_est:.2f}")
        st.markdown('</div>', unsafe_allow_html=True)

        # Recrée une carte avec la géométrie OSRM (pour l’effet wow)
        m2 = folium.Map(
            location=[path_latlon[0][0], path_latlon[0][1]],
            zoom_start=13, tiles="CartoDB Positron"
        )
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
            locations=path_latlon,  # [lat, lon] pour Leaflet/Folium
            color="#3A86FF", weight=5, opacity=0.9
        ).add_to(m2)
        st_folium(m2, height=520, width=800, key="uber_map_osrm_result", returned_objects=[])

        # Appel API tarif si dispo
        with st.spinner("Appel de l’API tarif…"):
            try:
                payload = make_payload(st.session_state.pickup, st.session_state.dropoff, trip_date, trip_time, passenger_count)
                result = call_fare_api(api_url, payload)
                fare = result.get("fare") or result.get("prediction") or result.get("y_pred")
                if fare is not None:
                    st.success("Prédiction reçue (API)")
                    st.metric("💵 Tarif estimé (API)", f"${float(fare):.2f}")
                else:
                    st.warning("API sans clé 'fare' — affichage estimation locale.")
                with st.expander("📦 Requête envoyée"):
                    st.json({"endpoint": api_url, "params": payload})
                with st.expander("📬 Réponse brute"):
                    st.json(result)
            except Exception as e:
                st.error(f"Échec API tarif: {e}")
                st.info(f"Tarif local de secours: **${local_est:.2f}**")

st.markdown("<hr>", unsafe_allow_html=True)
st.caption("Streamlit • Folium • streamlit-folium • Requests • OSRM — Itinéraire, distance & durée réelles.")
