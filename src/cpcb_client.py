"""Client for fetching real-time CPCB air-quality data for Nagpur.

Primary source: data.gov.in's "Real time Air Quality Index from various
locations" resource, which is published by CPCB and refreshed roughly hourly.
This resource returns one row per (station, pollutant) pair; use
`fetch_nagpur_station_rows` to get everything, or `fetch_nagpur_readings` for
a per-station summary with the computed overall AQI already attached.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

from src import config
from src.aqi_calc import overall_aqi_from_station_rows

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 20


class AQIFetchError(RuntimeError):
    """Raised when neither the primary nor fallback data source succeeds."""


def fetch_nagpur_station_rows(limit: int = 500) -> list[dict]:
    """Fetch raw (station, pollutant) rows for Nagpur from the CPCB feed.

    Raises AQIFetchError if the API key is missing or the request fails.
    """
    if not config.CPCB_API_KEY:
        raise AQIFetchError(
            "CPCB_API_KEY is not set. Create a .env file (see .env.example) "
            "with a free data.gov.in API key."
        )

    params = {
        "api-key": config.CPCB_API_KEY,
        "format": "json",
        "limit": limit,
        "filters[city]": config.CITY_NAME,
    }
    try:
        resp = requests.get(config.CPCB_API_BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise AQIFetchError(f"CPCB API request failed: {exc}") from exc

    payload = resp.json()
    records = payload.get("records", [])
    if not records:
        logger.warning("CPCB API returned no records for city=%s", config.CITY_NAME)
    return records


def fetch_nagpur_readings() -> list[dict]:
    """Group raw CPCB rows by station and attach the computed overall AQI.

    Returns a list of dicts:
        {station, latitude, longitude, last_update, aqi, category, color,
         dominant_pollutant, pollutants: {pollutant: avg_value, ...}}
    """
    rows = fetch_nagpur_station_rows()

    by_station: dict[str, list[dict]] = {}
    meta_by_station: dict[str, dict] = {}
    for row in rows:
        station = row.get("station", "Unknown station")
        by_station.setdefault(station, []).append(row)
        if station not in meta_by_station:
            meta_by_station[station] = {
                "latitude": _safe_float(row.get("latitude")),
                "longitude": _safe_float(row.get("longitude")),
                "last_update": row.get("last_update"),
            }

    readings = []
    for station, station_rows in by_station.items():
        overall = overall_aqi_from_station_rows(station_rows)
        if overall is None:
            continue
        meta = meta_by_station[station]
        pollutants = {
            r.get("pollutant_id"): _safe_float(r.get("pollutant_avg") or r.get("pollutant_max"))
            for r in station_rows
        }
        readings.append({
            "station": station,
            "latitude": meta["latitude"],
            "longitude": meta["longitude"],
            "last_update": meta["last_update"],
            "pollutants": pollutants,
            **overall,
        })
    return readings


def _safe_float(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# Optional fallback: WAQI (aqicn.org), used only if CPCB has no usable data
# for Nagpur and WAQI_API_TOKEN is configured.
# --------------------------------------------------------------------------

def fetch_nagpur_readings_waqi() -> list[dict]:
    if not config.WAQI_API_TOKEN:
        raise AQIFetchError("WAQI_API_TOKEN is not set; fallback source unavailable.")

    url = f"{config.WAQI_API_BASE_URL}/feed/{config.CITY_NAME}/"
    try:
        resp = requests.get(url, params={"token": config.WAQI_API_TOKEN}, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise AQIFetchError(f"WAQI API request failed: {exc}") from exc

    payload = resp.json()
    if payload.get("status") != "ok":
        raise AQIFetchError(f"WAQI API returned error status: {payload}")

    data = payload["data"]
    aqi = data.get("aqi")
    from src.aqi_calc import category_for_aqi
    label, color = category_for_aqi(float(aqi)) if aqi is not None else ("Unknown", "#95a5a6")
    iaqi = data.get("iaqi", {})
    return [{
        "station": data.get("city", {}).get("name", config.CITY_NAME),
        "latitude": data.get("city", {}).get("geo", [None, None])[0],
        "longitude": data.get("city", {}).get("geo", [None, None])[1],
        "last_update": data.get("time", {}).get("s"),
        "aqi": aqi,
        "category": label,
        "color": color,
        "dominant_pollutant": data.get("dominentpol"),
        "pollutants": {k: v.get("v") for k, v in iaqi.items()},
    }]


# Note: multi-source fallback orchestration now lives in src/data_sources.py,
# which tries OpenAQ, CPCB, and WAQI in the order set by
# config.DATA_SOURCE_PRIORITY. This module only implements the CPCB- and
# WAQI-specific fetch logic.
