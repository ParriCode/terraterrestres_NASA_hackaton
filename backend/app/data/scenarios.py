"""Escenarios iniciales de simulación."""
from datetime import timedelta
from typing import overload

from app.data.bodies import load_bodies
from app.data.ephemeris import get_body_time_pos
from app.models.domain import CelestialBody, SimulationConfig, Vec3, validate_non_negative

class Scenario:
    def __init__(self, config: SimulationConfig) -> None:
        self.config: SimulationConfig = config
        self.bodies: dict[str, CelestialBody] = load_bodies()

    @overload
    def get_body_pos(self, body: CelestialBody, time_s: float) -> Vec3: ...

    @overload
    def get_body_pos(self, body: str, time_s: float) -> Vec3: ...

    def get_body_pos(self, body: CelestialBody | str, time_s: float) -> Vec3:
        """Posición del cuerpo, time_s segundos después del inicio."""
        validate_non_negative(time_s, "time_s")
        body = self._validate_body(body)
        return get_body_time_pos(
            body, self.config.date + timedelta(seconds=time_s)
        )

    def _validate_body(self, body: CelestialBody | str) -> CelestialBody:
        if isinstance(body, str):
            key = body.strip().lower()
            try:
                return self.bodies[key]
            except KeyError as error:
                raise ValueError(
                    f"Cuerpo desconocido '{body}'. Disponibles: {', '.join(self.bodies)}"
                ) from error
        if not isinstance(body, CelestialBody):
            raise TypeError("body debe ser un CelestialBody o su nombre en el catálogo.")
        return body
