from datetime import date, time
from statistics import mean
from typing import Any

import httpx

from app.config import Settings
from app.spots import FishingSpot


WEATHER_HOURLY = [
    "temperature_2m",
    "pressure_msl",
    "cloud_cover",
    "rain",
    "precipitation",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
]

WEATHER_DAILY = ["sunrise", "sunset"]


def _parse_hour(value: str) -> int | None:
    try:
        return int(value.split("T", 1)[1].split(":", 1)[0])
    except (IndexError, ValueError):
        return None


def _time_window_indices(times: list[str], start_time: time | None, end_time: time | None) -> list[int]:
    start_hour = start_time.hour if start_time else 0
    end_hour = end_time.hour if end_time else 23
    if end_time and end_time.minute > 0:
        end_hour += 1
    return [
        idx
        for idx, timestamp in enumerate(times)
        if (hour := _parse_hour(timestamp)) is not None and start_hour <= hour <= min(end_hour, 23)
    ]


def _safe_values(hourly: dict[str, Any], key: str, indices: list[int]) -> list[float]:
    raw = hourly.get(key) or []
    values: list[float] = []
    for idx in indices:
        if idx < len(raw) and raw[idx] is not None:
            values.append(float(raw[idx]))
    return values


def summarize_weather(
    payload: dict[str, Any],
    start_time: time | None = None,
    end_time: time | None = None,
) -> dict[str, Any]:
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []
    indices = _time_window_indices(times, start_time, end_time)
    if not indices:
        indices = list(range(len(times)))

    pressure_values = _safe_values(hourly, "pressure_msl", indices)
    pressure_trend = None
    if len(pressure_values) >= 2:
        pressure_trend = round(pressure_values[-1] - pressure_values[0], 1)

    def avg(key: str) -> float | None:
        values = _safe_values(hourly, key, indices)
        return round(mean(values), 2) if values else None

    def total(key: str) -> float | None:
        values = _safe_values(hourly, key, indices)
        return round(sum(values), 2) if values else None

    def maximum(key: str) -> float | None:
        values = _safe_values(hourly, key, indices)
        return round(max(values), 2) if values else None

    daily = payload.get("daily") or {}
    sunrise = (daily.get("sunrise") or [None])[0]
    sunset = (daily.get("sunset") or [None])[0]

    return {
        "wind_speed": avg("wind_speed_10m"),
        "wind_direction": avg("wind_direction_10m"),
        "wind_gusts": maximum("wind_gusts_10m"),
        "air_temperature": avg("temperature_2m"),
        "pressure": avg("pressure_msl"),
        "pressure_trend": pressure_trend,
        "cloud_cover": avg("cloud_cover"),
        "rain": total("rain") if total("rain") is not None else total("precipitation"),
        "sunrise": sunrise,
        "sunset": sunset,
        "raw": payload,
    }


async def fetch_weather(
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
        "hourly": ",".join(WEATHER_HOURLY),
        "daily": ",".join(WEATHER_DAILY),
        "timezone": settings.timezone,
        "wind_speed_unit": "kmh",
        "timeformat": "iso8601",
    }
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        response = await client.get(settings.open_meteo_forecast_url, params=params)
        response.raise_for_status()
        payload = response.json()
    return summarize_weather(payload, start_time, end_time)
