import asyncio
from datetime import date, time
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.astronomy import moon_info
from app.config import Settings, get_settings
from app.forecast_engine import SPECIES_PROFILES, build_forecast
from app.marine import fetch_marine
from app.models import (
    ConditionsSnapshot,
    DataQuality,
    ForecastContextResponse,
    ForecastResponse,
    ReportIn,
    ReportOut,
    SeasonalSpeciesNote,
    SimilarReport,
)
from app.sheets import SheetsWriteNotConfigured, append_report, fetch_reports, filter_reports
from app.similarity import find_similar_reports
from app.spots import get_spot, list_spots
from app.weather import fetch_weather


app = FastAPI(
    title="AI Fishing Concierge API",
    version="0.1.0",
    description="Backend for Custom GPT Actions: shore spinning forecasts and fishing reports for Israel's Mediterranean coast.",
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def settings_dep() -> Settings:
    return get_settings()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "AI Fishing Concierge API"}


@app.get("/spots")
async def spots() -> dict[str, list[dict]]:
    return {"spots": list_spots()}


def _missing_condition_fields(conditions: ConditionsSnapshot) -> list[str]:
    return [key for key, value in conditions.model_dump().items() if value is None]


def _season_distance(month: int, active_months: list[int]) -> int:
    return min(min(abs(month - active), 12 - abs(month - active)) for active in active_months)


def _season_status(month: int, active_months: list[int]) -> str:
    if month in active_months:
        return "favorable"
    if _season_distance(month, active_months) <= 1:
        return "near-season"
    return "off-season"


def _seasonal_species_notes(month: int, target_species: str | None = None) -> list[SeasonalSpeciesNote]:
    notes = []
    for species, profile in SPECIES_PROFILES.items():
        if target_species and target_species.lower() not in species.lower():
            continue
        notes.append(
            SeasonalSpeciesNote(
                species=species,
                active_months=profile["months"],
                preferred_sea_temperature_c=list(profile["temp"]),
                season_status=_season_status(month, profile["months"]),
                recommended_lures=profile["lures"],
                behavior_clues=profile["likes"],
            )
        )
    return notes


def _recent_reports(reports: list[ReportOut], spot: str, limit: int = 8) -> list[ReportOut]:
    filtered = [report for report in reports if (report.spot or "").lower() == spot.lower()]
    filtered.sort(key=lambda report: report.date or "", reverse=True)
    return filtered[:limit]


async def _collect_forecast_inputs(
    settings: Settings,
    spot_name: str,
    forecast_date: date,
    start_time: time | None,
    end_time: time | None,
    target_species: str | None,
):
    fishing_spot = get_spot(spot_name)
    if not fishing_spot:
        raise HTTPException(status_code=404, detail="Unknown spot. Use Bat Yam or Jaffa.")

    warnings: list[str] = []
    weather: dict = {}
    marine: dict = {}

    weather_result, marine_result, reports_result = await asyncio.gather(
        fetch_weather(settings, fishing_spot, forecast_date, start_time, end_time),
        fetch_marine(settings, fishing_spot, forecast_date, start_time, end_time),
        fetch_reports(settings),
        return_exceptions=True,
    )

    weather_ok = not isinstance(weather_result, Exception)
    marine_ok = not isinstance(marine_result, Exception)
    reports_ok = not isinstance(reports_result, Exception)

    if isinstance(weather_result, Exception):
        warnings.append(f"Weather API unavailable: {weather_result.__class__.__name__}")
    else:
        weather = weather_result

    if isinstance(marine_result, Exception):
        warnings.append(f"Marine API unavailable: {marine_result.__class__.__name__}")
    else:
        marine = marine_result

    if isinstance(reports_result, Exception):
        warnings.append(f"Historical reports unavailable: {reports_result.__class__.__name__}")
        reports: list[ReportOut] = []
    else:
        reports = reports_result

    moon = moon_info(forecast_date)
    conditions = ConditionsSnapshot(
        wind_speed=weather.get("wind_speed"),
        wind_direction=weather.get("wind_direction"),
        wind_gusts=weather.get("wind_gusts"),
        air_temperature=weather.get("air_temperature"),
        pressure=weather.get("pressure"),
        pressure_trend=weather.get("pressure_trend"),
        cloud_cover=weather.get("cloud_cover"),
        rain=weather.get("rain"),
        wave_height=marine.get("wave_height"),
        wave_period=marine.get("wave_period"),
        wave_direction=marine.get("wave_direction"),
        sea_temperature=marine.get("sea_temperature"),
        tide_level=marine.get("tide_level"),
        sunrise=weather.get("sunrise"),
        sunset=weather.get("sunset"),
        moon_phase=moon.get("moon_phase"),
        moon_illumination=moon.get("moon_illumination"),
    )
    similar = find_similar_reports(
        reports=reports,
        spot=fishing_spot.name,
        target_date=forecast_date,
        wind_direction=weather.get("wind_direction"),
        wave_height=marine.get("wave_height"),
        sea_temperature=marine.get("sea_temperature"),
        target_species=target_species,
    )
    return fishing_spot, weather_ok, marine_ok, reports_ok, reports, similar, conditions, warnings, weather, marine, moon


def _build_legacy_baseline(
    fishing_spot,
    forecast_date: date,
    start_time: time | None,
    end_time: time | None,
    target_species: str | None,
    weather: dict,
    marine: dict,
    moon: dict,
    reports: list[ReportOut],
    similar: list[SimilarReport],
    warnings: list[str],
) -> ForecastResponse:
    return build_forecast(
        spot=fishing_spot,
        forecast_date=forecast_date,
        start_time=start_time,
        end_time=end_time,
        target_species=target_species,
        weather=weather,
        marine=marine,
        moon=moon,
        reports=reports,
        similar_reports=similar,
        warnings=warnings,
    )


@app.get("/forecast", response_model=ForecastResponse)
async def forecast(
    spot: Annotated[str, Query(description="Fishing spot: Bat Yam or Jaffa")],
    date_: Annotated[date, Query(alias="date", description="Forecast date in YYYY-MM-DD")],
    start_time: Annotated[time | None, Query(description="Optional start time HH:MM")] = None,
    end_time: Annotated[time | None, Query(description="Optional end time HH:MM")] = None,
    target_species: Annotated[str | None, Query(description="Optional species filter")] = None,
    settings: Settings = Depends(settings_dep),
) -> ForecastResponse:
    fishing_spot, _, _, _, reports, similar, _, warnings, weather, marine, moon = await _collect_forecast_inputs(
        settings, spot, date_, start_time, end_time, target_species
    )
    return _build_legacy_baseline(
        fishing_spot,
        date_,
        start_time,
        end_time,
        target_species,
        weather,
        marine,
        moon,
        reports,
        similar,
        warnings,
    )


@app.get("/forecast-context", response_model=ForecastContextResponse)
async def forecast_context(
    spot: Annotated[str, Query(description="Fishing spot: Bat Yam or Jaffa")],
    date_: Annotated[date, Query(alias="date", description="Forecast date in YYYY-MM-DD")],
    start_time: Annotated[time | None, Query(description="Optional start time HH:MM")] = None,
    end_time: Annotated[time | None, Query(description="Optional end time HH:MM")] = None,
    target_species: Annotated[str | None, Query(description="Optional species filter")] = None,
    settings: Settings = Depends(settings_dep),
) -> ForecastContextResponse:
    fishing_spot, weather_ok, marine_ok, reports_ok, reports, similar, conditions, warnings, _, _, _ = await _collect_forecast_inputs(
        settings, spot, date_, start_time, end_time, target_species
    )
    missing_data = _missing_condition_fields(conditions)
    notes = []
    if len(reports) < 10:
        notes.append("historical data is limited; use expert interpretation carefully")
    if not weather_ok or not marine_ok:
        notes.append("one or more external APIs failed; do not invent missing exact values")
    if not similar:
        notes.append("no close historical analogs were found")

    return ForecastContextResponse(
        purpose="Context package for an LLM-generated fishing forecast, not a final human-facing forecast.",
        llm_role=(
            "Use these backend facts as grounding. Apply fishing knowledge and reasoning to produce the final forecast, "
            "but separate observed/API facts from expert inference."
        ),
        spot=fishing_spot.name,
        date=date_.isoformat(),
        start_time=start_time.isoformat(timespec="minutes") if start_time else None,
        end_time=end_time.isoformat(timespec="minutes") if end_time else None,
        target_species=target_species,
        spot_profile=fishing_spot.to_dict(),
        conditions=conditions,
        api_raw_available={"weather": weather_ok, "marine": marine_ok, "historical_reports": reports_ok},
        data_quality=DataQuality(
            weather_api_ok=weather_ok,
            marine_api_ok=marine_ok,
            historical_reports_ok=reports_ok,
            historical_reports_count=len(reports),
            similar_reports_count=len(similar),
            missing_data=missing_data,
            notes=notes,
        ),
        seasonal_species_notes=_seasonal_species_notes(date_.month, target_species),
        recent_reports=_recent_reports(reports, fishing_spot.name),
        similar_reports=similar,
        warnings=warnings,
        llm_instructions=[
            "Do not invent exact weather, sea, moon, or historical report values that are null or missing.",
            "You, the LLM, must calculate bite scores and species probabilities yourself from the facts in this context.",
            "Do not treat backend /forecast scores as authoritative for this context response.",
            "Return probabilities and confidence, but explain they are LLM expert estimates, not API-calculated facts or guarantees.",
            "If historical_reports_count is low, explicitly say that local historical data is limited.",
            "Include safety warnings when reef, wind, swell, darkness, or access risks matter.",
            "Favor practical shore-spinning recommendations: species, best window, lures, retrieve, and where to cast.",
        ],
    )


@app.post("/report")
async def report(
    payload: ReportIn,
    settings: Settings = Depends(settings_dep),
) -> dict:
    fishing_spot = get_spot(payload.spot)
    if not fishing_spot:
        raise HTTPException(status_code=404, detail="Unknown spot. Use Bat Yam or Jaffa.")

    snapshot = ConditionsSnapshot(**moon_info(payload.date))
    try:
        weather_result, marine_result = await asyncio.gather(
            fetch_weather(settings, fishing_spot, payload.date, payload.start_time, payload.end_time),
            fetch_marine(settings, fishing_spot, payload.date, payload.start_time, payload.end_time),
            return_exceptions=True,
        )
        if not isinstance(weather_result, Exception):
            snapshot = snapshot.model_copy(update={key: value for key, value in weather_result.items() if key != "raw"})
        if not isinstance(marine_result, Exception):
            snapshot = snapshot.model_copy(update={key: value for key, value in marine_result.items() if key != "raw"})
    except Exception:
        pass

    try:
        result = append_report(settings, payload, snapshot)
    except SheetsWriteNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Google Sheets write failed: {exc.__class__.__name__}") from exc

    return {
        "status": "ok",
        "message": "Report appended to Google Sheets.",
        "updated_range": result.get("updates", {}).get("updatedRange"),
        "report": payload.model_dump(mode="json"),
        "conditions_snapshot": snapshot.model_dump(),
    }


@app.get("/reports", response_model=list[ReportOut])
async def reports(
    spot: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    species: str | None = None,
    angler_name: str | None = None,
    settings: Settings = Depends(settings_dep),
) -> list[ReportOut]:
    all_reports = await fetch_reports(settings)
    return filter_reports(all_reports, spot, date_from, date_to, species, angler_name)


@app.get("/similar-reports", response_model=list[SimilarReport])
async def similar_reports(
    spot: str,
    date_: Annotated[date | None, Query(alias="date")] = None,
    month: int | None = Query(default=None, ge=1, le=12),
    wind_direction: float | None = Query(default=None, ge=0, le=360),
    wave_height: float | None = Query(default=None, ge=0),
    sea_temperature: float | None = None,
    time_of_day: str | None = Query(default=None, pattern="^(dawn|day|dusk|night)$"),
    target_species: str | None = None,
    limit: int = Query(default=5, ge=1, le=20),
    settings: Settings = Depends(settings_dep),
) -> list[SimilarReport]:
    fishing_spot = get_spot(spot)
    if not fishing_spot:
        raise HTTPException(status_code=404, detail="Unknown spot. Use Bat Yam or Jaffa.")
    all_reports = await fetch_reports(settings)
    return find_similar_reports(
        reports=all_reports,
        spot=fishing_spot.name,
        target_date=date_,
        month=month,
        wind_direction=wind_direction,
        wave_height=wave_height,
        sea_temperature=sea_temperature,
        time_of_day=time_of_day,
        target_species=target_species,
        limit=limit,
    )
