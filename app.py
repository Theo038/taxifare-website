import streamlit as st

'''
# TaxiFareModel front
'''

st.markdown('''
Remember that there are several ways to output content into your web page...

Either as with the title by just creating a string (or an f-string). Or as with this paragraph using the `st.` functions
''')

'''
## Here we would like to add some controllers in order to ask the user to select the parameters of the ride

1. Let's ask for:
- date and time
- pickup longitude
- pickup latitude
- dropoff longitude
- dropoff latitude
- passenger count
'''

'''
## Once we have these, let's call our API in order to retrieve a prediction

See ? No need to load a `model.joblib` file in this app, we do not even need to know anything about Data Science in order to retrieve a prediction...

🤔 How could we call our API ? Off course... The `requests` package 💡
'''

url = 'https://taxifare.lewagon.ai/predict'

if url == 'https://taxifare.lewagon.ai/predict':

    st.markdown('Maybe you want to use your own API for the prediction, not the one provided by Le Wagon...')

'''

2. Let's build a dictionary containing the parameters for our API...

3. Let's call our API using the `requests` package...

4. Let's retrieve the prediction from the **JSON** returned by the API...

## Finally, we can display the prediction to the user
'''

import requests
from datetime import datetime, time, timezone

# ------------------------------------------------------------
# UI HEADER
# ------------------------------------------------------------
st.set_page_config(page_title="Taxi Fare Front", page_icon="🚕", layout="centered")

st.title("🚕 Taxi Fare Prediction")
st.markdown(
    """
    This app collects trip parameters and calls a prediction API to estimate the taxi fare.
    Use the controls below, then click **Predict fare**.
    """
)

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
    st.info(
        "Using the Le Wagon demo API. "
        "Set your own endpoint above to call a custom model."
    )

# ------------------------------------------------------------
# INPUT CONTROLS
# ------------------------------------------------------------
st.subheader("Trip parameters")

col_dt1, col_dt2 = st.columns(2)
trip_date = col_dt1.date_input("Date", value=datetime.now().date())
trip_time = col_dt2.time_input("Time", value=time(12, 0))

col1, col2 = st.columns(2)
pickup_longitude = col1.number_input("Pickup longitude", value=-73.985428, format="%.6f")
pickup_latitude  = col2.number_input("Pickup latitude",  value= 40.748817, format="%.6f")

col3, col4 = st.columns(2)
dropoff_longitude = col3.number_input("Dropoff longitude", value=-73.985428, format="%.6f")
dropoff_latitude  = col4.number_input("Dropoff latitude",  value= 40.758896, format="%.6f")

passenger_count = st.number_input("Passenger count", min_value=1, max_value=8, value=1, step=1)

# ------------------------------------------------------------
# BUILD PAYLOAD
# ------------------------------------------------------------
def make_payload() -> dict:
    """
    Create the query dict expected by typical /predict APIs:
    pickup_datetime, pickup_longitude, pickup_latitude,
    dropoff_longitude, dropoff_latitude, passenger_count
    """
    # Compose a UTC timestamp string like: "YYYY-MM-DD HH:MM:SS"
    # (Many demo endpoints expect this format; adapt if your API needs ISO 8601.)
    dt_local = datetime.combine(trip_date, trip_time)
    #dt_utc = dt_local.astimezone(timezone.utc)
    pickup_datetime = dt_local.strftime("%Y-%m-%d %H:%M:%S")

    payload = {
        "pickup_datetime":   pickup_datetime,
        "pickup_longitude":  float(pickup_longitude),
        "pickup_latitude":   float(pickup_latitude),
        "dropoff_longitude": float(dropoff_longitude),
        "dropoff_latitude":  float(dropoff_latitude),
        "passenger_count":   int(passenger_count),
    }
    return payload

# ------------------------------------------------------------
# CALL API
# ------------------------------------------------------------
def call_api(url: str, params: dict) -> dict:
    """
    Call the prediction API and return JSON.
    Expects { "fare": <float> } or similar.
    """
    # You can add an API key header if your backend needs it:
    # headers = {"Authorization": f"Bearer {os.getenv('TAXI_API_KEY')}"}
    headers = {"Accept": "application/json"}
    resp = requests.get(url, params=params, headers=headers, timeout=30)

    # Basic status handling
    if resp.status_code == 200:
        try:
            return resp.json()
        except Exception as e:
            raise RuntimeError(f"Invalid JSON in response: {e}") from e
    elif resp.status_code == 404:
        raise RuntimeError("Endpoint not found (404). Check your API URL.")
    elif resp.status_code == 422:
        raise RuntimeError("Validation error (422). Check your parameter ranges/format.")
    else:
        # Surface full error for debugging
        raise RuntimeError(f"API error {resp.status_code}: {resp.text}")

# ------------------------------------------------------------
# ACTIONS
# ------------------------------------------------------------
st.divider()
if st.button("Predict fare", type="primary"):
    # Basic input sanity checks
    errors = []
    if passenger_count < 1:
        errors.append("Passenger count must be ≥ 1.")
    # NYC approx bounds (adjust to your city if needed)
    if not (-180.0 <= pickup_longitude <= 180.0 and -90.0 <= pickup_latitude <= 90.0):
        errors.append("Pickup coordinates look out of bounds.")
    if not (-180.0 <= dropoff_longitude <= 180.0 and -90.0 <= dropoff_latitude <= 90.0):
        errors.append("Dropoff coordinates look out of bounds.")

    if errors:
        for e in errors:
            st.error(e)
    else:
        with st.spinner("Calling prediction API…"):
            try:
                payload = make_payload()
                result = call_api(api_url, payload)

                # Try common keys
                fare = result.get("fare") or result.get("prediction") or result.get("pred") or result.get("y_pred")

                if fare is None:
                    st.warning(f"API returned JSON but no 'fare' key was found:\n```\n{result}\n```")
                else:
                    st.success(f"💵 Estimated fare: **${float(fare):.2f}**")
                    with st.expander("Request details"):
                        st.json({"endpoint": api_url, "params": payload})
                    with st.expander("Raw API response"):
                        st.json(result)
            except Exception as e:
                st.error(f"Prediction failed: {e}")

# ------------------------------------------------------------
# FOOTER
# ------------------------------------------------------------
st.caption("Built with Streamlit • requests • UTC timestamps. Replace the endpoint to use your own model.")
