"""CPCB National AQI sub-index calculation and category/colour mapping.

Breakpoints are taken from the official CPCB methodology document
("AQI-FINAL-REPORT.pdf", https://cpcb.nic.in). Concentrations are in
micrograms per cubic metre (ug/m3) for all pollutants except CO, which is
in milligrams per cubic metre (mg/m3).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Each entry: (conc_low, conc_high, aqi_low, aqi_high)
BREAKPOINTS: dict[str, list[tuple[float, float, int, int]]] = {
    "PM10": [
        (0, 50, 0, 50),
        (51, 100, 51, 100),
        (101, 250, 101, 200),
        (251, 350, 201, 300),
        (351, 430, 301, 400),
        (431, 1000, 401, 500),
    ],
    "PM2.5": [
        (0, 30, 0, 50),
        (31, 60, 51, 100),
        (61, 90, 101, 200),
        (91, 120, 201, 300),
        (121, 250, 301, 400),
        (251, 500, 401, 500),
    ],
    "NO2": [
        (0, 40, 0, 50),
        (41, 80, 51, 100),
        (81, 180, 101, 200),
        (181, 280, 201, 300),
        (281, 400, 301, 400),
        (401, 1000, 401, 500),
    ],
    "SO2": [
        (0, 40, 0, 50),
        (41, 80, 51, 100),
        (81, 380, 101, 200),
        (381, 800, 201, 300),
        (801, 1600, 301, 400),
        (1601, 2500, 401, 500),
    ],
    "CO": [  # mg/m3
        (0, 1.0, 0, 50),
        (1.1, 2.0, 51, 100),
        (2.1, 10, 101, 200),
        (10.1, 17, 201, 300),
        (17.1, 34, 301, 400),
        (34.1, 50, 401, 500),
    ],
    "OZONE": [
        (0, 50, 0, 50),
        (51, 100, 51, 100),
        (101, 168, 101, 200),
        (169, 208, 201, 300),
        (209, 748, 301, 400),
        (749, 1000, 401, 500),
    ],
    "NH3": [
        (0, 200, 0, 50),
        (201, 400, 51, 100),
        (401, 800, 101, 200),
        (801, 1200, 201, 300),
        (1201, 1800, 301, 400),
        (1801, 2400, 401, 500),
    ],
    "PB": [
        (0, 0.5, 0, 50),
        (0.5, 1.0, 51, 100),
        (1.1, 2.0, 101, 200),
        (2.1, 3.0, 201, 300),
        (3.1, 3.5, 301, 400),
        (3.5, 5.0, 401, 500),
    ],
}

# Normalises the varied pollutant_id spellings returned by the CPCB feed
# (e.g. "PM2.5", "PM25", "Ozone", "OZONE", "NH3") onto the BREAKPOINTS keys.
POLLUTANT_ALIASES = {
    "PM2.5": "PM2.5",
    "PM25": "PM2.5",
    "PM10": "PM10",
    "NO2": "NO2",
    "SO2": "SO2",
    "CO": "CO",
    "OZONE": "OZONE",
    "O3": "OZONE",
    "NH3": "NH3",
    "PB": "PB",
}

CATEGORY_TABLE: list[tuple[int, int, str, str]] = [
    (0, 50, "Good", "#2ecc71"),
    (51, 100, "Satisfactory", "#a3d977"),
    (101, 200, "Moderate", "#f1c40f"),
    (201, 300, "Poor", "#e67e22"),
    (301, 400, "Very Poor", "#e74c3c"),
    (401, 500, "Severe", "#8e2443"),
]


@dataclass
class SubIndexResult:
    pollutant: str
    concentration: float
    sub_index: float


def normalize_pollutant(pollutant_id: str) -> Optional[str]:
    """Map a raw pollutant_id string from the API onto a BREAKPOINTS key."""
    if not pollutant_id:
        return None
    key = pollutant_id.strip().upper().replace(" ", "")
    return POLLUTANT_ALIASES.get(key)


def compute_sub_index(pollutant: str, concentration: float) -> Optional[float]:
    """Linear interpolation of a pollutant concentration onto the AQI scale."""
    table = BREAKPOINTS.get(pollutant)
    if table is None or concentration is None:
        return None
    try:
        concentration = float(concentration)
    except (TypeError, ValueError):
        return None
    if concentration < 0:
        return None

    for c_lo, c_hi, i_lo, i_hi in table:
        if c_lo <= concentration <= c_hi:
            if c_hi == c_lo:
                return float(i_lo)
            return round(((i_hi - i_lo) / (c_hi - c_lo)) * (concentration - c_lo) + i_lo, 1)

    # Above the top breakpoint: clamp to the worst (Severe) band's upper end,
    # scaled linearly past 500 so extreme pollution events are still visible.
    c_lo, c_hi, i_lo, i_hi = table[-1]
    if concentration > c_hi:
        return round(i_hi + (concentration - c_hi) * (i_hi - i_lo) / (c_hi - c_lo), 1)
    return None


def category_for_aqi(aqi: float) -> tuple[str, str]:
    """Return (category label, hex colour) for an overall AQI value."""
    for lo, hi, label, color in CATEGORY_TABLE:
        if lo <= aqi <= hi:
            return label, color
    if aqi > CATEGORY_TABLE[-1][1]:
        return CATEGORY_TABLE[-1][2], CATEGORY_TABLE[-1][3]
    return "Unknown", "#95a5a6"


def overall_aqi_from_station_rows(rows: list[dict]) -> Optional[dict]:
    """Given pollutant rows for one station (pollutant_id, avg value), compute
    the CPCB-style overall AQI as the maximum sub-index across pollutants.

    Each row is expected to have keys: "pollutant_id" and "pollutant_avg"
    (falls back to "pollutant_max" if avg is missing/non-numeric).
    """
    sub_indices: list[SubIndexResult] = []
    for row in rows:
        pollutant = normalize_pollutant(row.get("pollutant_id", ""))
        if pollutant is None:
            continue
        value = row.get("pollutant_avg") or row.get("pollutant_max")
        sub_idx = compute_sub_index(pollutant, value)
        if sub_idx is not None:
            sub_indices.append(SubIndexResult(pollutant, float(value), sub_idx))

    if not sub_indices:
        return None

    worst = max(sub_indices, key=lambda r: r.sub_index)
    label, color = category_for_aqi(worst.sub_index)
    return {
        "aqi": round(worst.sub_index),
        "category": label,
        "color": color,
        "dominant_pollutant": worst.pollutant,
        "sub_indices": {r.pollutant: r.sub_index for r in sub_indices},
    }
