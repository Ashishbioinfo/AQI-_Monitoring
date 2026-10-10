"""Nagpur Air Quality Index (AQI) monitoring dashboard.

Live station readings are pulled from the CPCB real-time feed (data.gov.in),
with WAQI as a fallback. Every successful fetch is also appended to a local
SQLite history table so that trend charts build up over time, even though
the live feed itself only exposes a current snapshot.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium
import folium

from src import config
from src.data_sources import fetch_nagpur_readings_with_fallback, AQIFetchError
from src.storage import insert_readings, get_history, get_stations, get_latest_snapshot

st.set_page_config(page_title="Nagpur AQI Monitor", page_icon="🌫️", layout="wide")

st.title("🌫️ Nagpur Air Quality Index (AQI) Monitor")
st.caption(
    "Live readings from CPCB monitoring stations (data.gov.in), AQI computed per the "
    "official CPCB National AQI formula. Historical trend builds up as this app (or the "
    "scheduled poller) runs over time."
)


@st.cache_data(ttl=900, show_spinner=False)  # 15 min in-memory cache
def _load_live_readings():
    return fetch_nagpur_readings_with_fallback()


def _render_api_key_help():
    st.warning(
        "No data source API key configured yet, so live data can't be fetched. "
        "OpenAQ is the easiest to set up (free, no government ID needed):\n\n"
        "1. Get a free key at https://explore.openaq.org/register\n"
        "2. Copy `.env.example` to `.env` in the project root\n"
        "3. Set `OPENAQ_API_KEY=<your key>`\n"
        "4. Restart the app\n\n"
        "(CPCB `data.gov.in` and WAQI are also supported as fallback sources — see README.)"
    )


# --------------------------------------------------------------------------
# Fetch (or fall back to last known DB snapshot) and persist for trending.
# --------------------------------------------------------------------------
readings: list[dict] = []
source = None
fetch_error = None

if not config.OPENAQ_API_KEY and not config.CPCB_API_KEY and not config.WAQI_API_TOKEN:
    _render_api_key_help()
else:
    try:
        readings, source = _load_live_readings()
        if readings:
            insert_readings(readings, source=source)
    except AQIFetchError as exc:
        fetch_error = str(exc)

if fetch_error:
    st.error(f"Live fetch failed: {fetch_error}")

if not readings:
    st.info("Showing the most recent locally stored snapshot instead (if any).")
    readings = get_latest_snapshot()
    source = "local cache"

if not readings:
    st.stop()

df = pd.DataFrame(readings)
st.caption(f"Data source: **{source}** · {len(df)} station(s) reporting · as of station `last_update` timestamps below.")

# --------------------------------------------------------------------------
# City-wide summary
# --------------------------------------------------------------------------
col1, col2, col3 = st.columns(3)
worst_row = df.loc[df["aqi"].idxmax()]
avg_aqi = round(df["aqi"].mean(), 1)

with col1:
    st.metric("Worst station AQI (Nagpur)", f"{int(worst_row['aqi'])}", worst_row["category"])
    st.caption(f"📍 {worst_row['station']}")
with col2:
    st.metric("City average AQI", f"{avg_aqi}")
with col3:
    st.metric("Stations reporting", f"{len(df)}")

# --------------------------------------------------------------------------
# Station map
# --------------------------------------------------------------------------
st.subheader("Station map")
map_df = df.dropna(subset=["latitude", "longitude"])
if not map_df.empty:
    center_lat = map_df["latitude"].mean() if len(map_df) else config.DEFAULT_MAP_CENTER[0]
    center_lon = map_df["longitude"].mean() if len(map_df) else config.DEFAULT_MAP_CENTER[1]
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=config.DEFAULT_MAP_ZOOM)
    for _, row in map_df.iterrows():
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=10,
            color=row.get("color", "#3388ff"),
            fill=True,
            fill_color=row.get("color", "#3388ff"),
            fill_opacity=0.85,
            popup=f"<b>{row['station']}</b><br>AQI: {int(row['aqi'])} ({row['category']})<br>Dominant: {row.get('dominant_pollutant', '-')}",
            tooltip=f"{row['station']}: AQI {int(row['aqi'])}",
        ).add_to(fmap)
    st_folium(fmap, height=480, use_container_width=True, returned_objects=[])
else:
    st.info("No station coordinates available to plot.")

# --------------------------------------------------------------------------
# Station detail: pollutant breakdown + historical trend
# --------------------------------------------------------------------------
st.subheader("Station detail")
station_names = sorted(df["station"].unique().tolist())
selected_station = st.selectbox("Select a station", station_names)

station_row = df[df["station"] == selected_station].iloc[0]

left, right = st.columns([1, 1])

with left:
    st.markdown(f"**Current AQI:** {int(station_row['aqi'])} — {station_row['category']}")
    st.markdown(f"**Dominant pollutant:** {station_row.get('dominant_pollutant', '-')}")
    st.markdown(f"**Last updated:** {station_row.get('last_update', '-')}")

    pollutants = station_row.get("pollutants") or {}
    poll_df = pd.DataFrame(
        [{"pollutant": k, "concentration": v} for k, v in pollutants.items() if v is not None]
    )
    if not poll_df.empty:
        fig = px.bar(poll_df, x="pollutant", y="concentration", title="Pollutant concentrations")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No pollutant breakdown available for this station.")

with right:
    hours = st.select_slider(
        "Trend window", options=[6, 12, 24, 48, 72, 168], value=24,
        format_func=lambda h: f"{h}h" if h < 168 else "7 days",
    )
    history = get_history(station=selected_station, since_hours=hours)
    if history:
        hist_df = pd.DataFrame(history)
        hist_df["fetched_at"] = pd.to_datetime(hist_df["fetched_at"])
        fig = px.line(hist_df, x="fetched_at", y="aqi", markers=True, title=f"AQI trend — {selected_station}")
        fig.update_yaxes(title="AQI")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(
            "No historical data yet for this station. History accumulates each time this "
            "app or `scripts/poll_and_store.py` fetches live data — check back after a few polls."
        )

with st.expander("All stations — current readings"):
    st.dataframe(
        df[["station", "aqi", "category", "dominant_pollutant", "last_update"]]
        .sort_values("aqi", ascending=False)
        .reset_index(drop=True),
        use_container_width=True,
    )
