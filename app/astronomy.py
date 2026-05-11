from datetime import date
from math import cos, floor, pi


MOON_PHASE_NAMES = [
    "new moon",
    "waxing crescent",
    "first quarter",
    "waxing gibbous",
    "full moon",
    "waning gibbous",
    "last quarter",
    "waning crescent",
]


def moon_info(day: date) -> dict[str, float | str]:
    """Return approximate lunar phase and illumination for fishing context."""
    known_new_moon_jd = 2451550.1
    synodic_month = 29.53058867

    year = day.year
    month = day.month
    dom = day.day
    if month <= 2:
        year -= 1
        month += 12
    a = floor(year / 100)
    b = 2 - a + floor(a / 4)
    jd = floor(365.25 * (year + 4716)) + floor(30.6001 * (month + 1)) + dom + b - 1524.5

    age = (jd - known_new_moon_jd) % synodic_month
    phase_fraction = age / synodic_month
    illumination = round((1 - cos(2 * pi * phase_fraction)) / 2 * 100, 1)
    phase_index = int((phase_fraction * 8) + 0.5) % 8
    return {
        "moon_phase": MOON_PHASE_NAMES[phase_index],
        "moon_illumination": illumination,
    }
