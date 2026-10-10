# Nagpur AQI Monitor

A Streamlit dashboard that tracks real-time and historical Air Quality Index
(AQI) for Nagpur, Maharashtra, using CPCB's official monitoring stations.

## What it does

- **Live AQI** per station, computed with the official **CPCB National AQI**
  formula (max sub-index across PM2.5, PM10, NO2, SO2, CO, O3, NH3, Pb — see
  `src/aqi_calc.py`).
- **Station map** colour-coded by AQI category (Good → Severe).
- **Pollutant breakdown** chart per station.
- **Historical trend chart** per station, built from a local SQLite database
  that accumulates a snapshot every time the app (or the scheduled poller
  script) fetches live data. The CPCB feed itself only exposes a current
  snapshot, not a history API, so this app builds its own time series.

## Data sources

1. **Primary: CPCB real-time feed via data.gov.in**
   Resource: "Real time Air Quality Index from various locations"
   (`https://www.data.gov.in/resource/real-time-air-quality-index-various-locations`)
   - Free, official Government of India source.
   - Get an API key: sign up at https://www.data.gov.in → *My Account → API Key*.
2. **Fallback: WAQI (aqicn.org)** — used automatically only if the CPCB feed
   has no usable Nagpur data (e.g. temporary outage) and `WAQI_API_TOKEN` is
   configured. Free token: https://aqicn.org/data-platform/token/

## Setup

```powershell
cd "C:\Desktop\AQI monitroing"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# edit .env and set CPCB_API_KEY=<your key>
streamlit run app.py
```

## Building up historical trends

The dashboard stores a snapshot on every page load, but for continuous trend
data (even while nobody has the dashboard open), schedule the poller:

```powershell
# Windows Task Scheduler, every 30 minutes:
schtasks /create /tn "NagpurAQIPoll" /tr "\"C:\Desktop\AQI monitroing\.venv\Scripts\python.exe\" \"C:\Desktop\AQI monitroing\scripts\poll_and_store.py\"" /sc minute /mo 30
```

On Linux/macOS, use a cron entry instead:
```
*/30 * * * * /path/to/.venv/bin/python /path/to/scripts/poll_and_store.py
```

## Project layout

```
AQI monitroing/
├── app.py                   # Streamlit dashboard
├── requirements.txt
├── .env.example             # copy to .env and fill in API keys
├── scripts/
│   └── poll_and_store.py    # scheduled job: fetch + append to history DB
├── src/
│   ├── config.py            # city/API/DB settings
│   ├── cpcb_client.py       # CPCB fetch + WAQI fallback
│   ├── aqi_calc.py          # official CPCB AQI breakpoints/formula
│   └── storage.py           # SQLite history read/write
└── data/
    └── aqi_history.db       # created automatically on first run (gitignored)
```

## Notes / limitations

- CPCB stations typically refresh ~hourly; polling more frequently than that
  will not surface new data, it just adds duplicate snapshots.
- If a station temporarily stops reporting a pollutant, its sub-index is
  simply excluded from that reading — the overall AQI for that station uses
  whichever pollutants are available.
- Breakpoints/category colours follow CPCB's official methodology document
  (CPCB "AQI-FINAL-REPORT.pdf"). Extreme values beyond the "Severe" band's
  upper breakpoint are extrapolated linearly rather than capped, so very
  large pollution spikes are still visible as a high number rather than
  pinned at 500.
