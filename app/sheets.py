import csv
import json
from io import StringIO
from typing import Any

import httpx
from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.config import Settings
from app.models import ConditionsSnapshot, ReportIn, ReportOut


REPORT_COLUMNS = [
    "angler_name",
    "spot",
    "date",
    "start_time",
    "end_time",
    "species_caught",
    "fish_count",
    "size_cm",
    "weight_kg",
    "lure_type",
    "lure_name",
    "lure_size_mm",
    "lure_weight_g",
    "lure_color",
    "retrieve_style",
    "water_clarity_score",
    "baitfish_presence_score",
    "bird_activity_score",
    "hits_count",
    "follows_count",
    "lost_fish_count",
    "notes",
    "created_at",
]

SNAPSHOT_COLUMNS = [
    "wind_speed",
    "wind_direction",
    "wind_gusts",
    "air_temperature",
    "pressure",
    "pressure_trend",
    "cloud_cover",
    "rain",
    "wave_height",
    "wave_period",
    "wave_direction",
    "sea_temperature",
    "tide_level",
    "sunrise",
    "sunset",
    "moon_phase",
    "moon_illumination",
]

ALL_COLUMNS = REPORT_COLUMNS + SNAPSHOT_COLUMNS
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
HEADER_ALIASES = {
    "species": "species_caught",
    "max_size_cm": "size_cm",
    "estimated_weight_kg": "weight_kg",
}


class SheetsWriteNotConfigured(RuntimeError):
    pass


def _normalize_key(key: str) -> str:
    return key.strip().lstrip("\ufeff").lower().replace(" ", "_").replace("-", "_")


def _empty_to_none(value: Any) -> Any:
    if value == "":
        return None
    return value


def _coerce_number(value: Any, number_type: type) -> Any:
    if value is None or value == "":
        return None
    try:
        return number_type(value)
    except (TypeError, ValueError):
        return value


def normalize_report_row(row: dict[str, Any]) -> ReportOut:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        normalized_key = _normalize_key(key)
        canonical_key = HEADER_ALIASES.get(normalized_key, normalized_key)
        if canonical_key not in normalized or normalized[canonical_key] in (None, ""):
            normalized[canonical_key] = _empty_to_none(value)
    known = {key: normalized.get(key) for key in REPORT_COLUMNS}
    for key in [
        "fish_count",
        "water_clarity_score",
        "baitfish_presence_score",
        "bird_activity_score",
        "hits_count",
        "follows_count",
        "lost_fish_count",
    ]:
        known[key] = _coerce_number(known.get(key), int)
    for key in ["size_cm", "weight_kg", "lure_size_mm", "lure_weight_g"]:
        known[key] = _coerce_number(known.get(key), float)
    extra = {key: value for key, value in normalized.items() if key not in REPORT_COLUMNS and value not in (None, "")}
    return ReportOut(**known, extra=extra)


async def fetch_reports(settings: Settings) -> list[ReportOut]:
    if settings.google_sheet_id:
        try:
            return fetch_reports_from_google_api(settings)
        except Exception:
            pass

    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        response = await client.get(settings.public_reports_csv_url)
        response.raise_for_status()
        text = response.text
    reader = csv.DictReader(StringIO(text))
    return [normalize_report_row(row) for row in reader]


def fetch_reports_from_google_api(settings: Settings) -> list[ReportOut]:
    service = _sheets_service(settings)
    headers = _ensure_headers(service, settings)
    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=settings.google_sheet_id,
            range=f"{settings.google_sheet_tab}!A:{_column_letter(len(headers))}",
        )
        .execute()
    )
    values = result.get("values", [])
    if not values:
        return []
    headers = values[0]
    reports = []
    for row in values[1:]:
        padded = row + [""] * max(0, len(headers) - len(row))
        reports.append(normalize_report_row(dict(zip(headers, padded))))
    return reports


def _credentials(settings: Settings):
    if settings.google_service_account_json:
        info = json.loads(settings.google_service_account_json)
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    if settings.google_service_account_file:
        return service_account.Credentials.from_service_account_file(
            settings.google_service_account_file,
            scopes=SCOPES,
        )
    raise SheetsWriteNotConfigured("Google Sheets write credentials are not configured.")


def _sheets_service(settings: Settings):
    creds = _credentials(settings)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _column_letter(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _read_headers(service: Any, settings: Settings) -> list[str]:
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=settings.google_sheet_id, range=f"{settings.google_sheet_tab}!1:1")
        .execute()
    )
    return result.get("values", [[]])[0]


def _ensure_headers(service: Any, settings: Settings) -> list[str]:
    headers = _read_headers(service, settings)
    if not headers:
        headers = ALL_COLUMNS
        service.spreadsheets().values().update(
            spreadsheetId=settings.google_sheet_id,
            range=f"{settings.google_sheet_tab}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [headers]},
        ).execute()
        return headers

    normalized_headers = {_normalize_key(header) for header in headers}
    missing = [column for column in ALL_COLUMNS if column not in normalized_headers]
    if missing:
        service.spreadsheets().values().update(
            spreadsheetId=settings.google_sheet_id,
            range=f"{settings.google_sheet_tab}!{_column_letter(len(headers) + 1)}1",
            valueInputOption="USER_ENTERED",
            body={"values": [missing]},
        ).execute()
        headers = headers + missing
    return headers


def _cell_value(value: Any) -> Any:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def append_report(settings: Settings, report: ReportIn, snapshot: ConditionsSnapshot | None = None) -> dict[str, Any]:
    if not settings.google_sheet_id:
        raise SheetsWriteNotConfigured("GOOGLE_SHEET_ID is not configured.")

    service = _sheets_service(settings)
    headers = _ensure_headers(service, settings)
    report_data = report.model_dump()
    snapshot_data = snapshot.model_dump() if snapshot else {}
    value_by_column = {**snapshot_data, **report_data}
    value_by_column["species"] = report_data.get("species_caught")
    value_by_column["max_size_cm"] = report_data.get("size_cm")
    value_by_column["estimated_weight_kg"] = report_data.get("weight_kg")
    if snapshot_data:
        value_by_column["weather_snapshot_json"] = json.dumps(snapshot_data, ensure_ascii=False)
    row = []
    for header in headers:
        header_key = _normalize_key(header)
        canonical_key = HEADER_ALIASES.get(header_key, header_key)
        row.append(_cell_value(value_by_column.get(header_key, value_by_column.get(canonical_key))))
    body = {"values": [row]}

    result = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=settings.google_sheet_id,
            range=f"{settings.google_sheet_tab}!A:{_column_letter(len(headers))}",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body,
        )
        .execute()
    )
    return result


def filter_reports(
    reports: list[ReportOut],
    spot: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    species: str | None = None,
    angler_name: str | None = None,
) -> list[ReportOut]:
    output = reports
    if spot:
        output = [row for row in output if (row.spot or "").lower() == spot.lower()]
    if date_from:
        output = [row for row in output if (row.date or "") >= date_from]
    if date_to:
        output = [row for row in output if (row.date or "") <= date_to]
    if species:
        output = [row for row in output if species.lower() in (row.species_caught or "").lower()]
    if angler_name:
        output = [row for row in output if angler_name.lower() in (row.angler_name or "").lower()]
    return output
