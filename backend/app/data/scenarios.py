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


class PlanarScenarioBody(ScenarioBody):
    """Movimiento 2D interpolado; conserva la interfaz usada por la física."""

    def __init__(self, body, date, times, positions, velocities):
        from scipy.interpolate import CubicHermiteSpline

        super().__init__(body, date)
        self._motion = CubicHermiteSpline(times, positions, velocities, extrapolate=False)
        self.duration_s = float(times[-1])

    def _check_time(self, time_s):
        validate_non_negative(time_s, "time_s")
        if time_s > self.duration_s:
            raise ValueError("Tiempo fuera de la tabla de efemérides.")

    def pos(self, time_s: float) -> Vec3:
        self._check_time(time_s)
        p = self._motion(time_s)
        return float(p[0]), float(p[1]), 0.0

    def speed(self, time_s: float) -> Vec3:
        self._check_time(time_s)
        v = self._motion(time_s, 1)
        return float(v[0]), float(v[1]), 0.0


class PlanarScenario:
    """Horizons proyectado en el plano orbital inicial, con ejes fijos.

    Origen: baricentro Tierra–Luna. X: Tierra→Luna inicial. Y: sentido del
    movimiento lunar inicial. Se omite la componente perpendicular al plano.
    La dinámica de la nave considera únicamente gravedad terrestre y lunar.
    """

    def __init__(self, date: datetime, duration_s: float, *, spacing_s=3600.0):
        import math
        import numpy as np
        from app.data.ephemeris import get_body_state_table
        from app.models.domain import validate_positive

        validate_positive(duration_s, "duration_s")
        validate_positive(spacing_s, "spacing_s")
        self.date, self.duration_s = date, duration_s
        catalog = load_bodies()
        intervals = max(2, math.ceil(duration_s / spacing_s))
        tables = {
            key: get_body_state_table(catalog[key], date,
                                     date + timedelta(seconds=duration_s), intervals)
            for key in ("earth", "moon")
        }
        relative_position = np.subtract(tables["moon"][1][0], tables["earth"][1][0])
        relative_velocity = np.subtract(tables["moon"][2][0], tables["earth"][2][0])
        x_axis = relative_position / np.linalg.norm(relative_position)
        normal = np.cross(relative_position, relative_velocity)
        if np.linalg.norm(normal) == 0:
            raise ValueError("No se puede definir el plano orbital inicial.")
        normal /= np.linalg.norm(normal)
        self.basis_icrf = np.stack((x_axis, np.cross(normal, x_axis)))
        self.bodies = {}
        for key, (times, positions, velocities) in tables.items():
            self.bodies[key] = PlanarScenarioBody(
                catalog[key], date, times,
                np.asarray(positions) @ self.basis_icrf.T,
                np.asarray(velocities) @ self.basis_icrf.T,
            )

    def get_bodies(self) -> list[ScenarioBody]:
        return list(self.bodies.values())
