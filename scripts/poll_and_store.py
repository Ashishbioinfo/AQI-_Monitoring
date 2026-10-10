"""Standalone script: fetch current Nagpur AQI readings and append them to
the local SQLite history DB. Intended to be run on a schedule (e.g. every
30 minutes via Windows Task Scheduler or cron) so the dashboard's
historical-trend charts have data to show.

Usage:
    python scripts/poll_and_store.py

Windows Task Scheduler (run every 30 min), from the project folder:
    schtasks /create /tn "NagpurAQIPoll" /tr "\"<path to venv>\\Scripts\\python.exe\" \"<project>\\scripts\\poll_and_store.py\"" /sc minute /mo 30
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_sources import fetch_nagpur_readings_with_fallback, AQIFetchError
from src.storage import insert_readings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    try:
        readings, source = fetch_nagpur_readings_with_fallback()
    except AQIFetchError as exc:
        logger.error("Failed to fetch AQI data: %s", exc)
        return 1

    if not readings:
        logger.warning("No readings returned; nothing stored.")
        return 0

    count = insert_readings(readings, source=source)
    logger.info("Stored %d station readings from %s.", count, source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
