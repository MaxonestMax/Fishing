from datetime import date
from typing import Any

from app.models import ReportOut, SimilarReport


def _month_from_report(report: ReportOut) -> int | None:
    if not report.date:
        return None
    try:
        return int(report.date.split("-", 2)[1])
    except (IndexError, ValueError):
        return None


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _circular_delta_degrees(a: float, b: float) -> float:
    diff = abs(a - b) % 360
    return min(diff, 360 - diff)


def _lure_summary(report: ReportOut) -> str | None:
    parts = [report.lure_name, report.lure_type]
    size = f"{report.lure_size_mm:g}mm" if report.lure_size_mm else None
    weight = f"{report.lure_weight_g:g}g" if report.lure_weight_g else None
    parts.extend([size, weight, report.lure_color])
    return " ".join(str(part) for part in parts if part)


def find_similar_reports(
    reports: list[ReportOut],
    spot: str,
    target_date: date | None = None,
    month: int | None = None,
    wind_direction: float | None = None,
    wave_height: float | None = None,
    sea_temperature: float | None = None,
    time_of_day: str | None = None,
    target_species: str | None = None,
    limit: int = 5,
) -> list[SimilarReport]:
    target_month = month or (target_date.month if target_date else None)
    scored: list[tuple[int, ReportOut]] = []

    for report in reports:
        score = 0
        if (report.spot or "").lower() == spot.lower():
            score += 30
        else:
            continue

        report_month = _month_from_report(report)
        if target_month and report_month:
            month_delta = min(abs(report_month - target_month), 12 - abs(report_month - target_month))
            score += max(0, 20 - month_delta * 5)

        if target_species and target_species.lower() in (report.species_caught or "").lower():
            score += 20

        extra = report.extra or {}
        report_wind_direction = _num(extra.get("wind_direction"))
        if wind_direction is not None and report_wind_direction is not None:
            score += max(0, int(15 - _circular_delta_degrees(wind_direction, report_wind_direction) / 12))

        report_wave_height = _num(extra.get("wave_height"))
        if wave_height is not None and report_wave_height is not None:
            score += max(0, int(10 - abs(wave_height - report_wave_height) * 8))

        report_sea_temperature = _num(extra.get("sea_temperature"))
        if sea_temperature is not None and report_sea_temperature is not None:
            score += max(0, int(10 - abs(sea_temperature - report_sea_temperature) * 2))

        if time_of_day and report.start_time:
            hour = int(report.start_time.split(":", 1)[0]) if ":" in report.start_time else None
            if hour is not None:
                bucket = "dawn" if 4 <= hour <= 8 else "day" if 9 <= hour <= 16 else "dusk" if 17 <= hour <= 20 else "night"
                if bucket == time_of_day.lower():
                    score += 10

        if score >= 35:
            scored.append((min(score, 100), report))

    scored.sort(key=lambda item: item[0], reverse=True)
    results: list[SimilarReport] = []
    for score, report in scored[:limit]:
        species = report.species_caught or "fish"
        lure = _lure_summary(report)
        lure_phrase = f" on {lure}" if lure else ""
        angler = report.angler_name or "An angler"
        spot_name = report.spot or spot
        summary = f"In similar conditions {angler} caught {species} at {spot_name}{lure_phrase}."
        results.append(
            SimilarReport(
                angler_name=report.angler_name,
                date=report.date,
                spot=report.spot,
                species=report.species_caught,
                lure=lure,
                summary=summary,
                similarity_score=score,
            )
        )
    return results
