from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Fishing Concierge API"
    app_version: str = "0.1.0"
    timezone: str = "Asia/Jerusalem"

    public_reports_csv_url: str = (
        "https://docs.google.com/spreadsheets/d/e/"
        "2PACX-1vRRGkYir-70KmoWwNkSV0zPulvDF97p9A7xb1prqNuqMk70B9_fPobp532gumbpO5OsdJ-ZSqtiq_zt/"
        "pub?output=csv"
    )

    google_sheet_id: str | None = None
    google_sheet_tab: str = "Reports"
    google_service_account_file: str | None = None
    google_service_account_json: str | None = None

    open_meteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    open_meteo_marine_url: str = "https://marine-api.open-meteo.com/v1/marine"
    request_timeout_seconds: float = 15.0

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", enable_decoding=False)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
