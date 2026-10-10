"""SQLite-backed storage for AQI readings, used to build historical trends.

The CPCB real-time feed only exposes a live snapshot (no history API), so
this module accumulates readings every time `poll_and_store.py` (or the
dashboard, on each load) runs, giving a growing time series per station.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from src import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at TEXT NOT NULL,
    station TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    last_update TEXT,
    aqi REAL,
    category TEXT,
    dominant_pollutant TEXT,
    pollutants_json TEXT,
    source TEXT
);
CREATE INDEX IF NOT EXISTS idx_readings_station_time ON readings (station, fetched_at);
"""


def _connect() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(_connect()) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def insert_readings(readings: list[dict], source: str) -> int:
    """Append a batch of station readings as one polling snapshot."""
    init_db()
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = [
        (
            fetched_at,
            r["station"],
            r.get("latitude"),
            r.get("longitude"),
            r.get("last_update"),
            r.get("aqi"),
            r.get("category"),
            r.get("dominant_pollutant"),
            json.dumps(r.get("pollutants", {})),
            source,
        )
        for r in readings
    ]
    with closing(_connect()) as conn:
        conn.executemany(
            """INSERT INTO readings
               (fetched_at, station, latitude, longitude, last_update, aqi,
                category, dominant_pollutant, pollutants_json, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
    return len(rows)


def get_stations() -> list[str]:
    init_db()
    with closing(_connect()) as conn:
        cur = conn.execute("SELECT DISTINCT station FROM readings ORDER BY station")
        return [row["station"] for row in cur.fetchall()]


def get_history(station: str | None = None, since_hours: int | None = None) -> list[dict]:
    init_db()
    query = "SELECT * FROM readings"
    clauses = []
    params: list = []
    if station:
        clauses.append("station = ?")
        params.append(station)
    if since_hours:
        clauses.append("fetched_at >= datetime('now', ?)")
        params.append(f"-{since_hours} hours")
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY fetched_at ASC"

    with closing(_connect()) as conn:
        cur = conn.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def get_latest_snapshot() -> list[dict]:
    """Return the most recent reading per station from the local DB
    (used as an offline fallback if a live fetch fails)."""
    init_db()
    with closing(_connect()) as conn:
        cur = conn.execute(
            """SELECT r.* FROM readings r
               INNER JOIN (
                   SELECT station, MAX(fetched_at) AS max_time
                   FROM readings GROUP BY station
               ) latest
               ON r.station = latest.station AND r.fetched_at = latest.max_time"""
        )
        return [dict(row) for row in cur.fetchall()]
