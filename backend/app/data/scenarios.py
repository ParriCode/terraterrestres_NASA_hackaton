"""Escenarios iniciales de simulación."""
from datetime import datetime, timedelta

from app.data.bodies import load_bodies
from app.data.ephemeris import get_body_time_pos, get_body_time_velocity
from app.models.domain import CelestialBody, SimulationConfig, Vec3, validate_non_negative

class ScenarioBody:
    """Cuerpo y movimiento relativo a la fecha inicial de un escenario."""

    def __init__(self, body: CelestialBody, date: datetime) -> None:
        self._body = body
        self.date = date

    @property
    def id(self) -> str:
        return self._body.id

    @property
    def name(self) -> str:
        return self._body.name

    @property
    def mu_m3_s2(self) -> float:
        return self._body.mu_m3_s2

    @property
    def radius_m(self) -> float:
        return self._body.radius_m

    def _instant(self, time_s: float) -> datetime:
        validate_non_negative(time_s, "time_s")
        return self.date + timedelta(seconds=time_s)

    def pos(self, time_s: float) -> Vec3:
        """Posición (x, y, z) en metros, time_s segundos desde el inicio."""
        return get_body_time_pos(self._body, self._instant(time_s))

    def speed(self, time_s: float) -> Vec3:
        """Vector de velocidad (vx, vy, vz) en m/s, no su magnitud."""
        return get_body_time_velocity(self._body, self._instant(time_s))


class Scenario:
    def __init__(self, config: SimulationConfig) -> None:
        self.config: SimulationConfig = config
        self.bodies: dict[str, ScenarioBody] = {
            body_id: ScenarioBody(body, config.date)
            for body_id, body in load_bodies().items()
        }

    def get_bodies(self) -> list[ScenarioBody]:
        return list(self.bodies.values())
