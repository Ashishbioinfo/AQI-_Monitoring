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

The app tries multiple sources in order (`src/config.py` →
`DATA_SOURCE_PRIORITY`, default `["openaq", "waqi", "cpcb"]`), automatically
falling back if one fails or isn't configured. **You only need one key to get
started — OpenAQ is the easiest.**

1. **OpenAQ (recommended, default primary)**
   - Free, open, non-profit aggregator — no commercial-use restriction.
   - Signup is just an email (no government ID): https://explore.openaq.org/register
   - Also re-publishes CPCB station data for India, so coverage for Nagpur is good.
2. **WAQI (aqicn.org)** — fallback.
   - Free for non-commercial use. Token: https://aqicn.org/data-platform/token/
3. **CPCB real-time feed via data.gov.in** — fallback, official Govt of India source.
   - Resource: "Real time Air Quality Index from various locations"
     (`https://www.data.gov.in/resource/real-time-air-quality-index-various-locations`)
   - Requires signing in via the **Janparichay** government SSO (My Account →
     API Key) — more signup friction than the other two, so it's not the
     default primary, but still supported if you'd rather use the official
     source.

## Setup

```powershell
cd "C:\Desktop\AQI monitroing"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# edit .env and set OPENAQ_API_KEY=<your key>
streamlit run app.py
```

## Deploying to Streamlit Community Cloud

1. Push this project to a GitHub repository.
2. Sign in at [share.streamlit.io](https://share.streamlit.io/) and create an app
   from that repository, selecting `app.py` as the main file.
3. In the app's **Settings → Secrets**, add at least one API key in TOML format:

   ```toml
   OPENAQ_API_KEY = "your OpenAQ key"
   # Optional fallback keys:
   CPCB_API_KEY = "your data.gov.in key"
   WAQI_API_TOKEN = "your WAQI token"
   ```

   Secrets are read from Streamlit's secrets store; the same values can still be
   supplied as environment variables or in a local `.env` file when running locally.
4. Deploy the app. The SQLite database is stored on the app's local filesystem,
   which Community Cloud may reset when the app restarts or is redeployed. Historical
   trends therefore aren't guaranteed to persist across restarts; use an external
   database if durable history is required.

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
