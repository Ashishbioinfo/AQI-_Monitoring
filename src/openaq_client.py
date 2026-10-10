"""Client for fetching real-time Nagpur air-quality data from OpenAQ (v3).

OpenAQ is a free, open, non-profit aggregator (no commercial-use
restriction) that ingests CPCB and other provider feeds. It requires a free
API key (header `X-API-Key`) — see https://explore.openaq.org/register.

Flow:
    1. GET /v3/locations?coordinates=lat,lon&radius=... -> station list with
       their sensors (pollutant + unit metadata).
    2. GET /v3/locations/{id}/latest -> latest value per sensor at that
       station.
    3. Join (1) and (2), convert units to the mg|ug/m3 basis expected by
       `src.aqi_calc`, and compute the overall AQI the same way the CPCB
       client does.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

from src import config
from src.aqi_calc import overall_aqi_from_station_rows

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 20

# Molar masses (g/mol) used to convert ppm/ppb gas readings to the ug/m3 (or
# mg/m3 for CO) basis that src.aqi_calc's CPCB breakpoints expect. Conversion
# assumes standard conditions (25 C, 1 atm): ug/m3 = ppb * molar_mass / 24.45.
MOLAR_MASS = {
    "NO2": 46.0055,
    "SO2": 64.066,
    "OZONE": 48.00,
    "CO": 28.01,
    "NH3": 17.03,
}


class AQIFetchError(RuntimeError):
    pass


def _headers() -> dict:
    if not config.OPENAQ_API_KEY:
        raise AQIFetchError(
            "OPENAQ_API_KEY is not set. Get a free key at "
            "https://explore.openaq.org/register and add it to your .env file."
        )
    return {"X-API-Key": config.OPENAQ_API_KEY}


def _get(path: str, params: dict) -> dict:
    url = f"{config.OPENAQ_API_BASE_URL}{path}"
    try:
        resp = requests.get(url, params=params, headers=_headers(), timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise AQIFetchError(f"OpenAQ API request failed ({path}): {exc}") from exc
    return resp.json()


def _fetch_locations() -> list[dict]:
    lat, lon = config.DEFAULT_MAP_CENTER
    payload = _get(
        "/locations",
        {
            "coordinates": f"{lat},{lon}",
            "radius": config.OPENAQ_SEARCH_RADIUS_METERS,
            "limit": 100,
        },
    )
    return payload.get("results", [])


def _fetch_latest_for_location(location_id: int) -> list[dict]:
    payload = _get(f"/locations/{location_id}/latest", {"limit": 1000})
    return payload.get("results", [])


def _normalize_unit_value(parameter_name: str, value: float, units: str) -> Optional[float]:
    """Convert a raw OpenAQ sensor value onto the basis CPCB breakpoints use
    (ug/m3 for everything except CO, which is mg/m3)."""
    if value is None:
        return None
    units_norm = (units or "").strip().lower().replace(" ", "")

    if parameter_name == "CO":
        if units_norm in ("mg/m3", "mg/m³"):
            return value
        if units_norm in ("ug/m3", "µg/m3", "ug/m³"):
            return value / 1000.0
        if units_norm == "ppm":
            return value * MOLAR_MASS["CO"] / 24.45
        if units_norm == "ppb":
            return value * MOLAR_MASS["CO"] / 24450.0
        return None

    # Everything else: target unit is ug/m3.
    if units_norm in ("ug/m3", "µg/m3", "ug/m³"):
        return value
    if units_norm in ("mg/m3", "mg/m³"):
        return value * 1000.0
    molar_mass = MOLAR_MASS.get(parameter_name)
    if molar_mass is None:
        return None
    if units_norm == "ppm":
        return value * 1000.0 * molar_mass / 24.45
    if units_norm == "ppb":
        return value * molar_mass / 24.45
    return None


def fetch_nagpur_readings() -> list[dict]:
    """Fetch current station readings for Nagpur from OpenAQ, with the
    overall CPCB-style AQI already computed per station."""
    locations = _fetch_locations()
    if not locations:
        logger.warning("OpenAQ returned no locations near Nagpur.")
        return []

    readings = []
    for loc in locations:
        location_id = loc.get("id")
        name = loc.get("name") or f"OpenAQ station {location_id}"
        coords = loc.get("coordinates") or {}

        sensor_meta = {}
        for sensor in loc.get("sensors", []):
            param = (sensor.get("parameter") or {})
            sensor_meta[sensor.get("id")] = {
                "name": (param.get("name") or "").strip().upper().replace(" ", ""),
                "units": param.get("units"),
            }

        try:
            latest = _fetch_latest_for_location(location_id)
        except AQIFetchError as exc:
            logger.warning("Skipping OpenAQ location %s: %s", location_id, exc)
            continue

        rows = []
        pollutants: dict[str, float] = {}
        last_update = None
        for entry in latest:
            sensor_id = entry.get("sensorsId")
            meta = sensor_meta.get(sensor_id)
            if not meta:
                continue
            raw_value = entry.get("value")
            converted = _normalize_unit_value(meta["name"], raw_value, meta["units"])
            if converted is None:
                continue
            rows.append({"pollutant_id": meta["name"], "pollutant_avg": converted})
            pollutants[meta["name"]] = converted
            dt = (entry.get("datetime") or {}).get("local") or (entry.get("datetime") or {}).get("utc")
            if dt and (last_update is None or dt > last_update):
                last_update = dt

        overall = overall_aqi_from_station_rows(rows)
        if overall is None:
            continue

        readings.append({
            "station": name,
            "latitude": coords.get("latitude"),
            "longitude": coords.get("longitude"),
            "last_update": last_update,
            "pollutants": pollutants,
            **overall,
        })

    return readings
