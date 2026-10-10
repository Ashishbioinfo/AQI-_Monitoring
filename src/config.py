"""Project-wide configuration for the Nagpur AQI monitoring app."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "aqi_history.db"

# City filter applied to the CPCB real-time dataset.
CITY_NAME = "Nagpur"
STATE_NAME = "Maharashtra"

# data.gov.in resource id for "Real time Air Quality Index from various locations".
CPCB_RESOURCE_ID = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
CPCB_API_BASE_URL = f"https://api.data.gov.in/resource/{CPCB_RESOURCE_ID}"
CPCB_API_KEY = os.environ.get("CPCB_API_KEY", "")

# Optional fallback provider.
WAQI_API_TOKEN = os.environ.get("WAQI_API_TOKEN", "")
WAQI_API_BASE_URL = "https://api.waqi.info"

# How often the polling script should be scheduled to run (minutes). CPCB
# stations typically refresh hourly, so polling more often than this is
# wasted effort; polling less often reduces trend resolution.
POLL_INTERVAL_MINUTES = 30

# Default map center (Nagpur city center) used when no station data is
# available yet.
DEFAULT_MAP_CENTER = (21.1458, 79.0882)
DEFAULT_MAP_ZOOM = 11
