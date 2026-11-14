"""Escenarios de simulación 2D y 3D respaldados por splines de efemérides."""

from datetime import datetime, timedelta
import math

import numpy as np
from scipy.interpolate import CubicHermiteSpline

from app.data.bodies import load_bodies
from app.data.ephemeris import get_body_state_table
from app.models.domain import (
    CelestialBody,
    SimulationConfig,
    Vec3,
    validate_non_negative,
    validate_positive,
)


class ScenarioBody:
    """Cuerpo celeste con trayectoria continua interpolada en el escenario."""

    def __init__(
        self,
        body: CelestialBody,
        date: datetime,
        times: np.ndarray,
        positions: np.ndarray,
        velocities: np.ndarray,
        *,
        planar: bool = False,
    ) -> None:
        self._body = body
        self.date = date
        self._planar = planar
        self._motion = CubicHermiteSpline(times, positions, velocities, extrapolate=False)
        self.duration_s = float(times[-1])

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

    def _check_time(self, time_s: float) -> None:
        validate_non_negative(time_s, "time_s")
        if time_s > self.duration_s:
            raise ValueError(f"Tiempo {time_s} s fuera de la tabla ({self.duration_s} s).")

    def pos(self, time_s: float) -> Vec3:
        """Posición (x, y, z) en metros, time_s segundos desde el inicio."""
        self._check_time(time_s)
        p = self._motion(time_s)
        if self._planar:
            return float(p[0]), float(p[1]), 0.0
        return float(p[0]), float(p[1]), float(p[2])

    def velocity(self, time_s: float) -> Vec3:
        """Vector de velocidad (vx, vy, vz) en m/s."""
        self._check_time(time_s)
        v = self._motion(time_s, 1)
        if self._planar:
            return float(v[0]), float(v[1]), 0.0
        return float(v[0]), float(v[1]), float(v[2])

    def speed(self, time_s: float) -> Vec3:
        """Alias de compatibilidad: devuelve el vector de velocidad (vx, vy, vz) en m/s."""
        return self.velocity(time_s)


def _build_interpolated_bodies(
    date: datetime,
    duration_s: float,
    spacing_s: float,
    basis: np.ndarray | None = None,
    planar: bool = False,
    body_ids: tuple[str, ...] | None = None,
) -> dict[str, ScenarioBody]:
    catalog = load_bodies()
    selected_ids = body_ids if body_ids is not None else tuple(catalog.keys())
    intervals = max(2, math.ceil(duration_s / spacing_s))
    stop_date = date + timedelta(seconds=duration_s)

    bodies: dict[str, ScenarioBody] = {}
    for key in selected_ids:
        if key not in catalog:
            continue
        times_t, pos_t, vel_t = get_body_state_table(catalog[key], date, stop_date, intervals)
        times = np.asarray(times_t, dtype=np.float64)
        times[-1] = float(duration_s)
        pos = np.asarray(pos_t, dtype=np.float64)
        vel = np.asarray(vel_t, dtype=np.float64)
        if basis is not None:
            pos = pos @ basis.T
            vel = vel @ basis.T
        bodies[key] = ScenarioBody(
            catalog[key], date, times, pos, vel, planar=planar
        )
    return bodies


def _initial_orbital_basis(date: datetime) -> np.ndarray:
    """Base ortonormal 3x3 alineada con el plano orbital inicial Tierra-Luna."""
    catalog = load_bodies()
    stop = date + timedelta(seconds=600)
    _, e_pos, e_vel = get_body_state_table(catalog["earth"], date, stop, 2)
    _, m_pos, m_vel = get_body_state_table(catalog["moon"], date, stop, 2)

    rel_pos = np.subtract(m_pos[0], e_pos[0])
    rel_vel = np.subtract(m_vel[0], e_vel[0])
    normal = np.cross(rel_pos, rel_vel)
    norm_val = np.linalg.norm(normal)
    if norm_val == 0.0:
        raise ValueError("No se puede definir el plano orbital inicial.")
    normal /= norm_val

    ref_axis = np.array((1.0, 0.0, 0.0))
    if abs(float(np.dot(ref_axis, normal))) > 0.99:
        ref_axis = np.array((0.0, 1.0, 0.0))

    x_axis = ref_axis - np.dot(ref_axis, normal) * normal
    x_axis /= np.linalg.norm(x_axis)
    y_axis = np.cross(normal, x_axis)
    return np.stack((x_axis, y_axis, normal))


class Scenario:
    """Escenario 3D en marco baricéntrico ICRF precargado con splines."""

    frame = "earth_moon_barycentric_inertial"

    def __init__(self, config: SimulationConfig, *, spacing_s: float = 600.0) -> None:
        self.config: SimulationConfig = config
        self.date = config.date
        self.duration_s = config.duration_s
        self.bodies: dict[str, ScenarioBody] = _build_interpolated_bodies(
            config.date, config.duration_s, spacing_s, planar=False
        )

    def get_bodies(self) -> list[ScenarioBody]:
        return list(self.bodies.values())

    def get_body_pos(self, body: ScenarioBody, t_s: float) -> Vec3:
        return body.pos(t_s)


class SpatialScenario:
    """Escenario 3D completo (Tierra, Luna y Sol) alineado con el plano orbital inicial."""

    frame = "earth_moon_barycentric_orbital_3d"

    def __init__(
        self,
        date: datetime,
        duration_s: float,
        *,
        spacing_s: float = 600.0,
        include_sun: bool = True,
    ) -> None:
        validate_positive(duration_s, "duration_s")
        validate_positive(spacing_s, "spacing_s")
        self.date = date
        self.duration_s = duration_s
        self.basis_icrf = _initial_orbital_basis(date)
        body_ids = ("earth", "moon", "sun") if include_sun else ("earth", "moon")
        self.bodies = _build_interpolated_bodies(
            date, duration_s, spacing_s, basis=self.basis_icrf, planar=False, body_ids=body_ids
        )

    def get_bodies(self) -> list[ScenarioBody]:
        return list(self.bodies.values())

    def get_body_pos(self, body: ScenarioBody, t_s: float) -> Vec3:
        return body.pos(t_s)


class PlanarScenario:
    """Horizons proyectado en el plano orbital inicial, con ejes fijos 2D."""

    frame = "earth_moon_barycentric_initial_orbital_plane"

    def __init__(
        self,
        date: datetime,
        duration_s: float,
        *,
        spacing_s: float = 600.0,
        include_sun: bool = True,
    ) -> None:
        validate_positive(duration_s, "duration_s")
        validate_positive(spacing_s, "spacing_s")
        self.date = date
        self.duration_s = duration_s
        basis_3d = _initial_orbital_basis(date)
        self.basis_icrf = basis_3d[:2]
        body_ids = ("earth", "moon", "sun") if include_sun else ("earth", "moon")
        self.bodies = _build_interpolated_bodies(
            date, duration_s, spacing_s, basis=self.basis_icrf, planar=True, body_ids=body_ids
        )

    def get_bodies(self) -> list[ScenarioBody]:
        return list(self.bodies.values())

    def get_body_pos(self, body: ScenarioBody, t_s: float) -> Vec3:
        return body.pos(t_s)