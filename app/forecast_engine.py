from datetime import date, time
from statistics import mean
from typing import Any

from app.models import ConditionsSnapshot, ForecastResponse, ReportOut, SimilarReport, SpeciesForecast
from app.spots import FishingSpot


SPECIES_PROFILES: dict[str, dict[str, Any]] = {
    "barracuda": {
        "months": [4, 5, 6, 7, 8, 9, 10, 11],
        "temp": (20, 29),
        "lures": ["minnow 110-140mm natural/silver", "topwater pencil early morning", "metal jig 20-30g if wind allows"],
        "likes": ["dawn", "dusk", "moderate chop", "baitfish"],
    },
    "leerfish / gombar": {
        "months": [5, 6, 7, 8, 9, 10],
        "temp": (22, 30),
        "lures": ["large topwater pencil 120-160mm", "stickbait 110-140mm", "fast minnow near bait schools"],
        "likes": ["baitfish", "warm water", "low light"],
    },
    "bluefish": {
        "months": [3, 4, 5, 9, 10, 11, 12],
        "temp": (18, 26),
        "lures": ["metal jig 20-40g", "minnow 100-130mm", "topwater when fish are chasing bait"],
        "likes": ["wind", "baitfish", "moving water"],
    },
    "sea bass / lavrak": {
        "months": [11, 12, 1, 2, 3, 4],
        "temp": (15, 22),
        "lures": ["soft plastic 3-5in natural", "shallow minnow 90-120mm", "small jighead around wash zones"],
        "likes": ["white water", "cooler water", "cloud cover"],
    },
    "grouper / locus": {
        "months": [4, 5, 6, 7, 8, 9, 10],
        "temp": (20, 29),
        "lures": ["soft plastic close to rocks", "slow jig 20-40g", "deep minnow around structure"],
        "likes": ["rocks", "structure", "clear water"],
    },
    "bonito / palamida": {
        "months": [9, 10, 11, 12, 1, 2, 3, 4],
        "temp": (17, 26),
        "lures": ["slim metal jig 20-40g fast retrieve", "small casting jig silver/blue", "compact minnow if bait is close"],
        "likes": ["baitfish", "birds", "clean water"],
    },
    "tuna": {
        "months": [5, 6, 7, 8, 9, 10, 11],
        "temp": (21, 29),
        "lures": ["long-cast metal jig 30-60g", "small stickbait when surface feeding", "heavy sinking pencil"],
        "likes": ["baitfish", "birds", "deep edge"],
    },
    "amberjack": {
        "months": [5, 6, 7, 8, 9, 10, 11],
        "temp": (21, 29),
        "lures": ["metal jig 30-60g", "sinking stickbait 100-140mm", "soft plastic around deeper rocks"],
        "likes": ["structure", "current", "depth"],
    },
    "needlefish": {
        "months": [4, 5, 6, 7, 8, 9, 10, 11],
        "temp": (20, 29),
        "lures": ["small pencil 70-100mm", "slim floating minnow", "micro jig 7-15g"],
        "likes": ["calm surface", "clear water", "baitfish"],
    },
    "dorado / mahi mahi": {
        "months": [8, 9, 10, 11],
        "temp": (24, 30),
        "lures": ["fast metal jig 20-40g", "bright minnow near floating debris", "small topwater if actively feeding"],
        "likes": ["late summer", "warm water", "offshore influence"],
    },
}


def _clamp(value: float, low: int = 0, high: int = 100) -> int:
    return int(max(low, min(high, round(value))))


def _is_low_light(start_time: time | None, end_time: time | None) -> bool:
    hours = [t.hour for t in [start_time, end_time] if t]
    if not hours:
        return True
    return any(hour <= 8 or hour >= 17 for hour in hours)


def _season_score(month: int, active_months: list[int]) -> int:
    if month in active_months:
        return 28
    distance = min(min(abs(month - active), 12 - abs(month - active)) for active in active_months)
    return max(0, 22 - distance * 8)


def _temp_score(sea_temp: float | None, preferred: tuple[int, int]) -> int:
    if sea_temp is None:
        return 8
    low, high = preferred
    if low <= sea_temp <= high:
        return 18
    distance = min(abs(sea_temp - low), abs(sea_temp - high))
    return max(0, int(16 - distance * 4))


def _history_score(species: str, reports: list[ReportOut], spot_name: str, month: int) -> tuple[int, int]:
    matches = []
    for report in reports:
        if (report.spot or "").lower() != spot_name.lower():
            continue
        if not report.date or len(report.date) < 7:
            continue
        try:
            report_month = int(report.date.split("-", 2)[1])
        except ValueError:
            continue
        month_delta = min(abs(report_month - month), 12 - abs(report_month - month))
        if month_delta <= 1 and species.split(" / ", 1)[0].lower() in (report.species_caught or "").lower():
            matches.append(report)
    catches = sum(report.fish_count or 0 for report in matches)
    contacts = sum((report.hits_count or 0) + (report.follows_count or 0) for report in matches)
    return min(14, catches * 3 + contacts), len(matches)


def _manual_context_score(reports: list[ReportOut], spot_name: str, month: int) -> tuple[int, list[str]]:
    relevant = []
    for report in reports:
        if (report.spot or "").lower() != spot_name.lower() or not report.date:
            continue
        try:
            report_month = int(report.date.split("-", 2)[1])
        except (IndexError, ValueError):
            continue
        if min(abs(report_month - month), 12 - abs(report_month - month)) <= 1:
            relevant.append(report)
    notes: list[str] = []
    score = 0
    bait = [row.baitfish_presence_score for row in relevant if row.baitfish_presence_score is not None]
    birds = [row.bird_activity_score for row in relevant if row.bird_activity_score is not None]
    clarity = [row.water_clarity_score for row in relevant if row.water_clarity_score is not None]
    if bait and mean(bait) >= 6:
        score += 6
        notes.append("recent historical notes show baitfish presence")
    if birds and mean(birds) >= 6:
        score += 4
        notes.append("bird activity has been positive in similar reports")
    if clarity and 4 <= mean(clarity) <= 8:
        score += 3
        notes.append("water clarity in similar reports was workable")
    return score, notes


def _conditions_text(snapshot: ConditionsSnapshot) -> str:
    parts = []
    if snapshot.wind_speed is not None:
        parts.append(f"wind {snapshot.wind_speed:g} km/h")
    if snapshot.wave_height is not None:
        parts.append(f"waves up to {snapshot.wave_height:g} m")
    if snapshot.sea_temperature is not None:
        parts.append(f"sea {snapshot.sea_temperature:g} C")
    if snapshot.pressure is not None:
        trend = ""
        if snapshot.pressure_trend is not None:
            trend = f", trend {snapshot.pressure_trend:+g} hPa"
        parts.append(f"pressure {snapshot.pressure:g} hPa{trend}")
    if snapshot.moon_phase:
        parts.append(f"{snapshot.moon_phase}, {snapshot.moon_illumination:g}% moon")
    return "; ".join(parts) if parts else "Some API parameters were unavailable; forecast uses seasonal and historical rules."


def _confidence(report_count: int, weather_ok: bool, marine_ok: bool) -> str:
    if weather_ok and marine_ok and report_count >= 15:
        return "high"
    if weather_ok and marine_ok and report_count >= 3:
        return "medium"
    if weather_ok or marine_ok:
        return "medium" if report_count >= 8 else "low"
    return "low"


def build_forecast(
    spot: FishingSpot,
    forecast_date: date,
    start_time: time | None,
    end_time: time | None,
    target_species: str | None,
    weather: dict[str, Any],
    marine: dict[str, Any],
    moon: dict[str, Any],
    reports: list[ReportOut],
    similar_reports: list[SimilarReport],
    warnings: list[str],
) -> ForecastResponse:
    snapshot = ConditionsSnapshot(
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

    month = forecast_date.month
    low_light = _is_low_light(start_time, end_time)
    manual_score, manual_notes = _manual_context_score(reports, spot.name, month)
    species_items: list[SpeciesForecast] = []
    warnings = list(warnings)

    if len(reports) < 10:
        warnings.append("historical data is limited; forecast relies mostly on rule-based seasonal and weather scoring")

    if snapshot.wave_height is not None and snapshot.wave_height >= 1.2 and spot.name == "Bat Yam":
        warnings.append("High surf may be unsafe on reef")
    if snapshot.wind_gusts is not None and snapshot.wind_gusts >= 35:
        warnings.append("Strong gusts may reduce casting control and increase reef risk")

    for species, profile in SPECIES_PROFILES.items():
        if target_species and target_species.lower() not in species.lower():
            continue

        score = 20
        reasons = []
        season = _season_score(month, profile["months"])
        score += season
        reasons.append("season is favorable" if season >= 25 else "season is marginal")

        temp_score = _temp_score(snapshot.sea_temperature, profile["temp"])
        score += temp_score
        if snapshot.sea_temperature is not None:
            reasons.append(f"sea temperature is {snapshot.sea_temperature:g} C")
        else:
            reasons.append("sea temperature is unavailable")

        if low_light:
            score += 8
            reasons.append("low-light window improves shore spinning odds")

        if snapshot.wave_height is not None:
            if 0.3 <= snapshot.wave_height <= 1.0:
                score += 8
                reasons.append("moderate surf can push bait toward rocks")
            elif snapshot.wave_height > 1.4:
                score -= 12
                reasons.append("surf may be too high for precise shore spinning")

        if snapshot.wind_speed is not None:
            if 6 <= snapshot.wind_speed <= 22:
                score += 5
                reasons.append("wind is fishable and adds surface movement")
            elif snapshot.wind_speed > 30:
                score -= 10
                reasons.append("wind may make lure control difficult")

        if snapshot.cloud_cover is not None and snapshot.cloud_cover >= 50:
            score += 3
            reasons.append("cloud cover extends low-light behavior")

        if snapshot.pressure_trend is not None and abs(snapshot.pressure_trend) <= 2:
            score += 3
            reasons.append("pressure is relatively stable")

        history, species_report_count = _history_score(species, reports, spot.name, month)
        score += history + manual_score
        if history:
            reasons.append(f"similar historical reports include {species_report_count} relevant catches or contacts")
        if manual_notes:
            reasons.extend(manual_notes[:2])

        if len(reports) < 10:
            score = min(score, 82)
        if species_report_count == 0:
            score = min(score, 78)
        probability = _clamp(score)
        best_time = "dawn/dusk" if low_light else "first and last light if schedule allows"
        confidence = _confidence(species_report_count, bool(weather), bool(marine))
        species_items.append(
            SpeciesForecast(
                species=species,
                probability=probability,
                confidence=confidence,
                best_time=best_time,
                recommended_lures=profile["lures"],
                reason="; ".join(dict.fromkeys(reasons)),
            )
        )

    species_items.sort(key=lambda item: item.probability, reverse=True)
    overall_score = _clamp(mean([item.probability for item in species_items[:5]]) if species_items else 0)
    return ForecastResponse(
        spot=spot.name,
        date=forecast_date.isoformat(),
        overall_score=overall_score,
        conditions_summary=_conditions_text(snapshot),
        conditions=snapshot,
        species_forecast=species_items,
        similar_reports=similar_reports,
        warnings=list(dict.fromkeys(warnings)),
    )
