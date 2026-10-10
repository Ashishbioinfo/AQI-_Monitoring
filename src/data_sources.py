"""Orchestrates fetching Nagpur AQI readings across multiple data sources,
trying each in the order given by `config.DATA_SOURCE_PRIORITY` and falling
back to the next source on error or empty results.

Add a new source by giving it a `fetch_nagpur_readings() -> list[dict]`
function (returning the same shape used across this project: station,
latitude, longitude, last_update, aqi, category, color,
dominant_pollutant, pollutants) and registering it in `_SOURCES` below.
"""
from __future__ import annotations

import logging

from src import config
from src.aqi_calc import category_for_aqi

logger = logging.getLogger(__name__)


class AQIFetchError(RuntimeError):
    """Raised when every configured data source fails."""


def _fetch_openaq() -> list[dict]:
    from src.openaq_client import fetch_nagpur_readings
    return fetch_nagpur_readings()


def _fetch_cpcb() -> list[dict]:
    from src.cpcb_client import fetch_nagpur_readings
    return fetch_nagpur_readings()


def _fetch_waqi() -> list[dict]:
    from src.cpcb_client import fetch_nagpur_readings_waqi
    return fetch_nagpur_readings_waqi()


_SOURCES = {
    "openaq": ("OpenAQ", _fetch_openaq),
    "cpcb": ("CPCB (data.gov.in)", _fetch_cpcb),
    "waqi": ("WAQI (aqicn.org)", _fetch_waqi),
}


def fetch_nagpur_readings_with_fallback() -> tuple[list[dict], str]:
    """Try each source in `config.DATA_SOURCE_PRIORITY` order.

    Returns (readings, source_label) from the first source that returns
    non-empty results. Raises AQIFetchError if every source fails/returns
    nothing.
    """
    errors = []
    for key in config.DATA_SOURCE_PRIORITY:
        entry = _SOURCES.get(key)
        if entry is None:
            continue
        label, fetch_fn = entry
        try:
            readings = fetch_fn()
        except Exception as exc:  # noqa: BLE001 - want to try next source on any failure
            logger.warning("%s fetch failed: %s", label, exc)
            errors.append(f"{label}: {exc}")
            continue
        if readings:
            return readings, label
        logger.info("%s returned no readings; trying next source.", label)

    raise AQIFetchError(
        "All configured data sources failed or returned no data.\n" + "\n".join(errors)
    )


__all__ = ["fetch_nagpur_readings_with_fallback", "AQIFetchError", "category_for_aqi"]
