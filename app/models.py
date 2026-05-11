from datetime import date, datetime, time, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Confidence = Literal["low", "medium", "high"]


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    angler_name: str | None = None
    spot: str
    date: date
    start_time: time | None = None
    end_time: time | None = None
    species_caught: str | None = None
    fish_count: int | None = Field(default=None, ge=0)
    size_cm: float | None = Field(default=None, ge=0)
    weight_kg: float | None = Field(default=None, ge=0)
    lure_type: str | None = None
    lure_name: str | None = None
    lure_size_mm: float | None = Field(default=None, ge=0)
    lure_weight_g: float | None = Field(default=None, ge=0)
    lure_color: str | None = None
    retrieve_style: str | None = None
    water_clarity_score: int | None = Field(default=None, ge=1, le=10)
    baitfish_presence_score: int | None = Field(default=None, ge=1, le=10)
    bird_activity_score: int | None = Field(default=None, ge=1, le=10)
    hits_count: int | None = Field(default=None, ge=0)
    follows_count: int | None = Field(default=None, ge=0)
    lost_fish_count: int | None = Field(default=None, ge=0)
    notes: str | None = None
    created_at: datetime | None = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("created_at", mode="after")
    @classmethod
    def default_created_at(cls, value: datetime | None) -> datetime:
        return value or datetime.now(timezone.utc)


class ReportOut(BaseModel):
    angler_name: str | None = None
    spot: str | None = None
    date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    species_caught: str | None = None
    fish_count: int | None = None
    size_cm: float | None = None
    weight_kg: float | None = None
    lure_type: str | None = None
    lure_name: str | None = None
    lure_size_mm: float | None = None
    lure_weight_g: float | None = None
    lure_color: str | None = None
    retrieve_style: str | None = None
    water_clarity_score: int | None = None
    baitfish_presence_score: int | None = None
    bird_activity_score: int | None = None
    hits_count: int | None = None
    follows_count: int | None = None
    lost_fish_count: int | None = None
    notes: str | None = None
    created_at: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ConditionsSnapshot(BaseModel):
    wind_speed: float | None = None
    wind_direction: float | None = None
    wind_gusts: float | None = None
    air_temperature: float | None = None
    pressure: float | None = None
    pressure_trend: float | None = None
    cloud_cover: float | None = None
    rain: float | None = None
    wave_height: float | None = None
    wave_period: float | None = None
    wave_direction: float | None = None
    sea_temperature: float | None = None
    tide_level: float | None = None
    sunrise: str | None = None
    sunset: str | None = None
    moon_phase: str | None = None
    moon_illumination: float | None = None


class SpeciesForecast(BaseModel):
    species: str
    probability: int = Field(ge=0, le=100)
    confidence: Confidence
    best_time: str | None = None
    recommended_lures: list[str]
    reason: str


class SimilarReport(BaseModel):
    angler_name: str | None = None
    date: str | None = None
    spot: str | None = None
    species: str | None = None
    lure: str | None = None
    summary: str
    similarity_score: int = Field(ge=0, le=100)


class ForecastResponse(BaseModel):
    spot: str
    date: str
    overall_score: int = Field(ge=0, le=100)
    conditions_summary: str
    conditions: ConditionsSnapshot
    species_forecast: list[SpeciesForecast]
    similar_reports: list[SimilarReport]
    warnings: list[str]


class SeasonalSpeciesNote(BaseModel):
    species: str
    active_months: list[int]
    preferred_sea_temperature_c: list[int]
    season_status: Literal["favorable", "near-season", "off-season"]
    recommended_lures: list[str]
    behavior_clues: list[str]


class DataQuality(BaseModel):
    weather_api_ok: bool
    marine_api_ok: bool
    historical_reports_ok: bool
    historical_reports_count: int
    similar_reports_count: int
    missing_data: list[str]
    notes: list[str]


class ForecastContextResponse(BaseModel):
    purpose: str
    llm_role: str
    spot: str
    date: str
    start_time: str | None = None
    end_time: str | None = None
    target_species: str | None = None
    spot_profile: dict[str, Any]
    conditions: ConditionsSnapshot
    api_raw_available: dict[str, bool]
    data_quality: DataQuality
    seasonal_species_notes: list[SeasonalSpeciesNote]
    recent_reports: list[ReportOut]
    similar_reports: list[SimilarReport]
    warnings: list[str]
    llm_instructions: list[str]
