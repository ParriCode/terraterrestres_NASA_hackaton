"""Cuerpos que ORBITAL 4B obtiene de JPL Horizons."""

from dataclasses import dataclass


HORIZONS_API_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
HORIZONS_TIMEOUT_S = 20.0


@dataclass(frozen=True)
class HorizonsBodyConfig:
    id: str
    name: str
    horizons_id: str
    radius_pattern: str
    mass_pattern: str
    mass_scale_kg: float


CELESTIAL_BODIES = (
    HorizonsBodyConfig(
        id="earth",
        name="Earth",
        horizons_id="399",
        radius_pattern=r"Vol\.\s*Mean\s+Radius\s*\(km\)\s*=\s*([0-9.]+)",
        mass_pattern=r"Mass\s*x10\^24\s*\(kg\)\s*=\s*([0-9.]+)",
        mass_scale_kg=1e24,
    ),
    HorizonsBodyConfig(
        id="moon",
        name="Moon",
        horizons_id="301",
        radius_pattern=r"Vol\.\s*mean\s+radius,\s*km\s*=\s*([0-9.]+)",
        mass_pattern=r"Mass,\s*x10\^22\s*kg\s*=\s*([0-9.]+)",
        mass_scale_kg=1e22,
    ),
    HorizonsBodyConfig(
        id="sun",
        name="Sun",
        horizons_id="10",
        radius_pattern=r"Vol\.\s*mean\s+radius\s*\(km\)\s*=\s*([0-9.]+)",
        mass_pattern=r"Mass,\s*10\^24\s*kg\s*=\s*~?([0-9.]+)",
        mass_scale_kg=1e24,
    ),
)