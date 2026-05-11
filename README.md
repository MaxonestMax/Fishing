# AI Fishing Concierge Backend

FastAPI backend for a Custom GPT Action focused on shore spinning in the Mediterranean Sea, Israel.

## Features

- `GET /health` checks that the backend is alive.
- `GET /spots` returns Bat Yam and Jaffa spot metadata.
- `GET /forecast` combines weather, marine conditions, seasonality, spot geometry, and historical Google Sheets reports.
- `GET /forecast-context` returns the grounding package that a Custom GPT should use to make the final LLM forecast.
- `POST /report` appends a structured fishing report to Google Sheets.
- `GET /reports` reads historical reports from the published CSV.
- `GET /similar-reports` finds similar reports by spot, season, wind, waves, sea temperature, time of day, and species.

Report storage is append-only by design. The API exposes no update or delete endpoints. Corrections should be written as new rows with explanatory notes.

The first scoring version is deliberately rule-based. It does not claim certainty, always returns confidence, and warns when API or historical data is limited.

## Project Structure

```text
app/
  main.py
  config.py
  models.py
  spots.py
  weather.py
  marine.py
  astronomy.py
  sheets.py
  forecast_engine.py
  similarity.py
```

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Open:

- API health: `http://127.0.0.1:8000/health`
- Swagger docs: `http://127.0.0.1:8000/docs`
- FastAPI OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

Example forecast:

```bash
curl "http://127.0.0.1:8000/forecast?spot=Bat%20Yam&date=2026-05-15&start_time=05:00&end_time=08:00"
```

## Data Sources

Weather and sunrise/sunset use Open-Meteo Forecast API.

Marine data uses Open-Meteo Marine API:

- wave height
- wave period
- wave direction
- sea surface temperature
- sea level height, used as a rough tide/sea-level proxy where available

Moon phase and moon illumination are calculated locally with an approximate lunar cycle formula.

Historical reports are read from the published Google Sheet CSV:

```text
https://docs.google.com/spreadsheets/d/e/2PACX-1vRRGkYir-70KmoWwNkSV0zPulvDF97p9A7xb1prqNuqMk70B9_fPobp532gumbpO5OsdJ-ZSqtiq_zt/pub?output=csv
```

## Google Sheets API Setup For Writing

The published CSV is read-only. `POST /report` needs write access through Google Sheets API.

1. Open Google Cloud Console.
2. Create or select a project.
3. Enable **Google Sheets API**.
4. Create a **Service Account**.
5. Create a JSON key for the service account.
6. Open the editable Google Sheet in Google Drive.
7. Share the spreadsheet with the service account email, usually something like:

```text
your-service-account@your-project.iam.gserviceaccount.com
```

8. Give it Editor access.
9. Put the editable spreadsheet ID into `.env`:

```env
GOOGLE_SHEET_ID="your_editable_spreadsheet_id"
GOOGLE_SHEET_TAB="Reports"
```

10. For local development, use:

```env
GOOGLE_SERVICE_ACCOUNT_FILE="C:\path\to\service-account.json"
```

For Render, use `GOOGLE_SERVICE_ACCOUNT_JSON` instead and paste the full JSON as a single environment variable.

## Append-Only Safety

The backend is intentionally append-only:

- `POST /report` can add a new row.
- No endpoint can delete rows.
- No endpoint can edit existing rows.
- Custom GPT instructions tell the GPT to append corrections as new rows.

For friend access, do not give friends Editor access to the Google Sheet unless you trust them with the raw database. Let them use the Custom GPT instead. The service account needs Editor access so the backend can append rows, but that permission should not be shared with normal users.

## Recommended Google Sheet Columns

Use this header row in the `Reports` tab:

```csv
angler_name,spot,date,start_time,end_time,species_caught,fish_count,size_cm,weight_kg,lure_type,lure_name,lure_size_mm,lure_weight_g,lure_color,retrieve_style,water_clarity_score,baitfish_presence_score,bird_activity_score,hits_count,follows_count,lost_fish_count,notes,created_at,wind_speed,wind_direction,wind_gusts,air_temperature,pressure,pressure_trend,cloud_cover,rain,wave_height,wave_period,wave_direction,sea_temperature,tide_level,sunrise,sunset,moon_phase,moon_illumination
```

## Deploy To Render.com

1. Push this folder to GitHub.
2. In Render, create a new **Web Service**.
3. Connect the GitHub repository.
4. Use:

```text
Build Command: pip install -r requirements.txt
Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

5. Add environment variables from `.env.example`.
6. Set at minimum:

```env
TIMEZONE=Asia/Jerusalem
PUBLIC_REPORTS_CSV_URL=...
GOOGLE_SHEET_ID=...
GOOGLE_SHEET_TAB=Reports
GOOGLE_SERVICE_ACCOUNT_JSON=...
```

7. Deploy and test:

```text
https://YOUR-RENDER-SERVICE.onrender.com/health
```

## Connect To Custom GPT Actions

1. Deploy the backend.
2. Open `openapi-actions.yaml`.
3. Replace:

```yaml
servers:
  - url: https://YOUR-RENDER-SERVICE.onrender.com
```

with your real Render URL.

4. In the Custom GPT builder, add a new Action.
5. Import the OpenAPI schema from `openapi-actions.yaml`.
6. Authentication can stay **None** for the first private prototype.
7. Paste `custom-gpt-system-prompt.md` into the Custom GPT instructions.

For a public deployment, add API-key authentication before sharing the GPT broadly.

## LLM Forecast Architecture

Use `/forecast-context` as the main Action for prediction. The backend gathers facts:

- spot profile
- weather and marine API data
- sunrise/sunset and moon
- historical reports
- similar reports
- seasonal species notes
- rule-based baseline
- data quality and missing fields

The Custom GPT then performs the final fishing interpretation. It may use general fishing knowledge, but it must not invent exact missing API values or pretend that limited history is strong evidence.

## Forecast Notes

The forecast is a fishing decision aid, not a guarantee. It combines:

- seasonality by species
- sea temperature fit
- low-light timing
- wave height and wind usability
- pressure stability
- spot geometry and safety
- historical catches, hits, follows, baitfish, birds, and clarity when reports exist

When historical reports are limited, the response explicitly says so.
