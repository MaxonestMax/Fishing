from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class FishingSpot:
    name: str
    latitude: float
    longitude: float
    fishing_type: str
    depth_m: str
    bottom: str
    geometry_notes: str
    good_for: list[str]
    safety_notes: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


SPOTS: dict[str, FishingSpot] = {
    "bat yam": FishingSpot(
        name="Bat Yam",
        latitude=32.0150,
        longitude=34.7385,
        fishing_type="shore fishing",
        depth_m="2-4",
        bottom="sand + rocks",
        geometry_notes="Angler often stands on reef; shallow reef edge with sand pockets and rocks.",
        good_for=["shore spinning", "light jigging", "minnows", "topwater", "soft plastics"],
        safety_notes=[
            "Reef can become unsafe with high surf or long-period swell.",
            "Use extra caution in darkness and on wet rock.",
        ],
    ),
    "jaffa": FishingSpot(
        name="Jaffa",
        latitude=32.0520,
        longitude=34.7485,
        fishing_type="shore fishing",
        depth_m="3-7",
        bottom="sand + rocks",
        geometry_notes="Rocky shoreline and harbor-adjacent structure with deeper edges than Bat Yam.",
        good_for=["shore spinning", "rock fishing", "jigs", "minnows", "soft plastics"],
        safety_notes=[
            "Rock platforms can be slippery in swell.",
            "Check local access and safety conditions before fishing.",
        ],
    ),
}


def list_spots() -> list[dict]:
    return [spot.to_dict() for spot in SPOTS.values()]


def get_spot(name: str) -> FishingSpot | None:
    return SPOTS.get(name.strip().lower())
