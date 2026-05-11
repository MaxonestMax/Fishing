from datetime import date, time
from statistics import mean
from typing import Any

import httpx

from app.config import Settings
from app.spots import FishingSpot
from app.weather import _safe_values, _time_window_indices


MARINE_HOURLY = [
    "wave_height",
    "wave_direction",
    "wave_period",
    "sea_surface_temperature",
    "sea_level_height_msl",
]


def summarize_marine(
    payload: dict[str, Any],
    start_time: time | None = None,
    end_time: time | None = None,
) -> dict[str, Any]:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    indices = _time_window_indices(times, start_time, end_time)
    if not indices:
        indices = list(range(len(times)))

    def avg(key: str) -> float | None:
        values = _safe_values(hourly, key, indices)
        return round(mean(values), 2) if values else None

    def maximum(key: str) -> float | None:
        values = _safe_values(hourly, key, indices)
        return round(max(values), 2) if values else None

    return {
        "wave_height": maximum("wave_height"),
        "wave_direction": avg("wave_direction"),
        "wave_period": avg("wave_period"),
        "sea_temperature": avg("sea_surface_temperature"),
        "tide_level": avg("sea_level_height_msl"),
        "raw": payload,
    }


async def fetch_marine(
    settings: Settings,
    spot: FishingSpot,
    forecast_date: date,
    start_time: time | None = None,
    end_time: time | None = None,
) -> dict[str, Any]:
    params = {
        "latitude": spot.latitude,
        "longitude": spot.longitude,
        "start_date": forecast_date.isoformat(),
        "end_date": forecast_date.isoformat(),
        "hourly": ",".join(MARINE_HOURLY),
        "timezone": settings.timezone,
        "timeformat": "iso8601",
    }
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        response = await client.get(settings.open_meteo_marine_url, params=params)
        response.raise_for_status()
        payload = response.json()
    return summarize_marine(payload, start_time, end_time)
