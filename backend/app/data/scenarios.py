"""Escenarios iniciales de simulación y proyección planar con efemérides Horizons."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import math

import numpy as np

from app.data import ephemeris
from app.data.bodies import load_bodies
from app.data.ephemeris import get_body_time_pos, get_body_time_velocity
from app.models.domain import (
    CelestialBody,
    SimulationConfig,
    Vec3,
    validate_non_negative,
    validate_positive,
)

_DEFAULT_GET_BODY_TIME_POS = get_body_time_pos
_DEFAULT_GET_BODY_TIME_VELOCITY = get_body_time_velocity
_MAX_HORIZONS_INTERVALS = 10_000


class _UniformHermite2D:
    """Evaluador cúbico de Hermite O(1) en malla temporal uniforme (plano XY)."""

    def __init__(self, times, positions, velocities) -> None:
        self._n_intervals = len(times) - 1
        self.duration_s = float(times[-1])
        self._dt = self.duration_s / self._n_intervals
        self._inv_dt = 1.0 / self._dt

        pos = np.asarray(positions, dtype=float)[:, :2]
        vel = np.asarray(velocities, dtype=float)[:, :2]
        p0, p1 = pos[:-1], pos[1:]
        m0, m1 = vel[:-1] * self._dt, vel[1:] * self._dt

        c0 = p0
        c1 = m0
        c2 = 3.0 * (p1 - p0) - 2.0 * m0 - m1
        c3 = 2.0 * (p0 - p1) + m0 + m1

        # Arrays (N, 2) para evaluación vectorizada en bloque (pos_array)
        self._c0 = c0
        self._c1 = c1
        self._c2 = c2
        self._c3 = c3

        # Tuplas nativas para acceso escalar O(1) sin overhead de NumPy (pos_xy / vel_xy)
        self._c0x: tuple[float, ...] = tuple(c0[:, 0].tolist())
        self._c1x: tuple[float, ...] = tuple(c1[:, 0].tolist())
        self._c2x: tuple[float, ...] = tuple(c2[:, 0].tolist())
        self._c3x: tuple[float, ...] = tuple(c3[:, 0].tolist())

        self._c0y: tuple[float, ...] = tuple(c0[:, 1].tolist())
        self._c1y: tuple[float, ...] = tuple(c1[:, 1].tolist())
        self._c2y: tuple[float, ...] = tuple(c2[:, 1].tolist())
        self._c3y: tuple[float, ...] = tuple(c3[:, 1].tolist())

    def pos_xy(self, time_s: float) -> tuple[float, float]:
        u = time_s * self._inv_dt
        idx = int(u)
        if idx >= self._n_intervals:
            idx = self._n_intervals - 1
        elif idx < 0:
            idx = 0
        s = u - idx
        x = self._c0x[idx] + s * (self._c1x[idx] + s * (self._c2x[idx] + s * self._c3x[idx]))
        y = self._c0y[idx] + s * (self._c1y[idx] + s * (self._c2y[idx] + s * self._c3y[idx]))
        return x, y

    def vel_xy(self, time_s: float) -> tuple[float, float]:
        u = time_s * self._inv_dt
        idx = int(u)
        if idx >= self._n_intervals:
            idx = self._n_intervals - 1
        elif idx < 0:
            idx = 0
        s = u - idx
        inv_dt = self._inv_dt
        vx = (self._c1x[idx] + s * (2.0 * self._c2x[idx] + 3.0 * s * self._c3x[idx])) * inv_dt
        vy = (self._c1y[idx] + s * (2.0 * self._c2y[idx] + 3.0 * s * self._c3y[idx])) * inv_dt
        return vx, vy

    def pos_array(self, times: np.ndarray) -> np.ndarray:
        t = np.asarray(times, dtype=float)
        u = t * self._inv_dt
        idx = np.clip(u.astype(np.intp), 0, self._n_intervals - 1)
        s = (u - idx)[:, None]
        xy = self._c0[idx] + s * (self._c1[idx] + s * (self._c2[idx] + s * self._c3[idx]))
        out = np.zeros((len(t), 3), dtype=float)
        out[:, :2] = xy
        return out


class _UniformHermite3D:
    """Evaluador cúbico de Hermite O(1) en malla temporal uniforme (espacio 3D)."""

    def __init__(self, times, positions, velocities) -> None:
        self._n_intervals = len(times) - 1
        self.duration_s = float(times[-1])
        self._dt = self.duration_s / self._n_intervals
        self._inv_dt = 1.0 / self._dt

        pos = np.asarray(positions, dtype=float)
        vel = np.asarray(velocities, dtype=float)
        p0, p1 = pos[:-1], pos[1:]
        m0, m1 = vel[:-1] * self._dt, vel[1:] * self._dt

        c0 = p0
        c1 = m0
        c2 = 3.0 * (p1 - p0) - 2.0 * m0 - m1
        c3 = 2.0 * (p0 - p1) + m0 + m1

        self._c0x: tuple[float, ...] = tuple(c0[:, 0].tolist())
        self._c1x: tuple[float, ...] = tuple(c1[:, 0].tolist())
        self._c2x: tuple[float, ...] = tuple(c2[:, 0].tolist())
        self._c3x: tuple[float, ...] = tuple(c3[:, 0].tolist())

        self._c0y: tuple[float, ...] = tuple(c0[:, 1].tolist())
        self._c1y: tuple[float, ...] = tuple(c1[:, 1].tolist())
        self._c2y: tuple[float, ...] = tuple(c2[:, 1].tolist())
        self._c3y: tuple[float, ...] = tuple(c3[:, 1].tolist())

        self._c0z: tuple[float, ...] = tuple(c0[:, 2].tolist())
        self._c1z: tuple[float, ...] = tuple(c1[:, 2].tolist())
        self._c2z: tuple[float, ...] = tuple(c2[:, 2].tolist())
        self._c3z: tuple[float, ...] = tuple(c3[:, 2].tolist())

    def pos(self, time_s: float) -> Vec3:
        u = time_s * self._inv_dt
        idx = int(u)
        if idx >= self._n_intervals:
            idx = self._n_intervals - 1
        elif idx < 0:
            idx = 0
        s = u - idx
        x = self._c0x[idx] + s * (self._c1x[idx] + s * (self._c2x[idx] + s * self._c3x[idx]))
        y = self._c0y[idx] + s * (self._c1y[idx] + s * (self._c2y[idx] + s * self._c3y[idx]))
        z = self._c0z[idx] + s * (self._c1z[idx] + s * (self._c2z[idx] + s * self._c3z[idx]))
        return (x, y, z)

    def vel(self, time_s: float) -> Vec3:
        u = time_s * self._inv_dt
        idx = int(u)
        if idx >= self._n_intervals:
            idx = self._n_intervals - 1
        elif idx < 0:
            idx = 0
        s = u - idx
        inv_dt = self._inv_dt
        vx = (self._c1x[idx] + s * (2.0 * self._c2x[idx] + 3.0 * s * self._c3x[idx])) * inv_dt
        vy = (self._c1y[idx] + s * (2.0 * self._c2y[idx] + 3.0 * s * self._c3y[idx])) * inv_dt
        vz = (self._c1z[idx] + s * (2.0 * self._c2z[idx] + 3.0 * s * self._c3z[idx])) * inv_dt
        return (vx, vy, vz)


class ScenarioBody:
    """Cuerpo y movimiento relativo a la fecha inicial de un escenario 3D."""

    def __init__(
        self,
        body: CelestialBody,
        date: datetime,
        *,
        duration_s: float | None = None,
        spacing_s: float = 3600.0,
        preload_callback=None,
    ) -> None:
        self._body = body
        self.date = date
        self._duration_s = duration_s
        self._spacing_s = spacing_s
        self._preload_callback = preload_callback
        self._motion3d: _UniformHermite3D | None = None

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

    def _set_table(self, times, positions, velocities) -> None:
        self._motion3d = _UniformHermite3D(times, positions, velocities)

    def _ensure_motion3d(self) -> _UniformHermite3D | None:
        if self._motion3d is not None:
            return self._motion3d
        if self._duration_s is None or self._duration_s <= 0.0:
            return None
        if self._preload_callback is not None:
            self._preload_callback()
            return self._motion3d

        intervals = min(
            _MAX_HORIZONS_INTERVALS,
            max(2, math.ceil(self._duration_s / self._spacing_s)),
        )
        times, positions, velocities = ephemeris.get_body_state_table(
            self._body,
            self.date,
            self.date + timedelta(seconds=self._duration_s),
            intervals,
        )
        self._set_table(times, positions, velocities)
        return self._motion3d

    def _instant(self, time_s: float) -> datetime:
        validate_non_negative(time_s, "time_s")
        return self.date + timedelta(seconds=time_s)

    @staticmethod
    def _uses_default_ephemeris() -> bool:
        # Permite que tests con monkeypatch en scenarios.* o ephemeris.* usen el fallback
        return (
            get_body_time_pos is _DEFAULT_GET_BODY_TIME_POS
            and get_body_time_velocity is _DEFAULT_GET_BODY_TIME_VELOCITY
            and ephemeris.get_body_time_pos is _DEFAULT_GET_BODY_TIME_POS
            and ephemeris.get_body_time_velocity is _DEFAULT_GET_BODY_TIME_VELOCITY
        )

    def pos(self, time_s: float) -> Vec3:
        """Posición (x, y, z) en metros, time_s segundos desde el inicio."""
        validate_non_negative(time_s, "time_s")
        if self._uses_default_ephemeris():
            motion = self._ensure_motion3d()
            if motion is not None and time_s <= motion.duration_s:
                return motion.pos(time_s)
        return get_body_time_pos(self._body, self._instant(time_s))

    def speed(self, time_s: float) -> Vec3:
        """Vector de velocidad (vx, vy, vz) en m/s, no su magnitud."""
        validate_non_negative(time_s, "time_s")
        if self._uses_default_ephemeris():
            motion = self._ensure_motion3d()
            if motion is not None and time_s <= motion.duration_s:
                return motion.vel(time_s)
        return get_body_time_velocity(self._body, self._instant(time_s))


class Scenario:
    """Escenario 3D en ICRF con precarga en lote de tablas Horizons."""

    def __init__(
        self,
        config: SimulationConfig,
        *,
        spacing_s: float = 3600.0,
        preload: bool = False,
    ) -> None:
        validate_positive(spacing_s, "spacing_s")
        self.config: SimulationConfig = config
        self._spacing_s = spacing_s
        self._tables_loaded = False

        catalog = load_bodies()
        self.bodies: dict[str, ScenarioBody] = {
            body_id: ScenarioBody(
                body,
                config.date,
                duration_s=config.duration_s,
                spacing_s=spacing_s,
                preload_callback=self._preload_tables,
            )
            for body_id, body in catalog.items()
        }
        if preload:
            self._preload_tables()

    def _preload_tables(self) -> None:
        if self._tables_loaded or not self.bodies:
            return

        duration_s = self.config.duration_s
        intervals = min(
            _MAX_HORIZONS_INTERVALS,
            max(2, math.ceil(duration_s / self._spacing_s)),
        )
        start = self.config.date
        stop = start + timedelta(seconds=duration_s)
        items = list(self.bodies.values())

        def fetch(scenario_body: ScenarioBody):
            return scenario_body, ephemeris.get_body_state_table(
                scenario_body._body, start, stop, intervals
            )

        if len(items) == 1:
            sb, table = fetch(items[0])
            sb._set_table(*table)
        else:
            with ThreadPoolExecutor(max_workers=len(items)) as pool:
                for sb, table in pool.map(fetch, items):
                    sb._set_table(*table)

        self._tables_loaded = True

    def get_bodies(self) -> list[ScenarioBody]:
        return list(self.bodies.values())


class PlanarScenarioBody(ScenarioBody):
    """Movimiento 2D interpolado en O(1); conserva la interfaz usada por la física."""

    def __init__(self, body: CelestialBody, date: datetime, times, positions, velocities) -> None:
        super().__init__(body, date)
        self._motion = _UniformHermite2D(times, positions, velocities)
        self.duration_s = self._motion.duration_s

    def _check_time(self, time_s: float) -> None:
        validate_non_negative(time_s, "time_s")
        if time_s > self.duration_s:
            raise ValueError("Tiempo fuera de la tabla de efemérides.")

    def pos_xy_fast(self, time_s: float) -> tuple[float, float]:
        """Acceso rápido sin validación de dominio para el bucle interno de DOP853."""
        return self._motion.pos_xy(time_s)

    def pos_array(self, times: np.ndarray) -> np.ndarray:
        """Evaluación vectorizada en bloque para longitudes y muestreo de API."""
        return self._motion.pos_array(times)

    def pos(self, time_s: float) -> Vec3:
        self._check_time(time_s)
        x, y = self._motion.pos_xy(time_s)
        return (x, y, 0.0)

    def speed(self, time_s: float) -> Vec3:
        self._check_time(time_s)
        vx, vy = self._motion.vel_xy(time_s)
        return (vx, vy, 0.0)


class PlanarScenario:
    """Horizons proyectado en el plano orbital inicial, con ejes fijos.

    Origen: baricentro Tierra–Luna. X: Tierra→Luna inicial. Y: sentido del
    movimiento lunar inicial. Se omite la componente perpendicular al plano.
    La dinámica de la nave considera únicamente gravedad terrestre y lunar.
    """

    def __init__(self, date: datetime, duration_s: float, *, spacing_s: float = 3600.0) -> None:
        validate_positive(duration_s, "duration_s")
        validate_positive(spacing_s, "spacing_s")
        self.date = date
        self.duration_s = duration_s

        catalog = load_bodies()
        intervals = min(
            _MAX_HORIZONS_INTERVALS,
            max(2, math.ceil(duration_s / spacing_s)),
        )
        stop = date + timedelta(seconds=duration_s)

        def fetch_table(key: str):
            return key, ephemeris.get_body_state_table(catalog[key], date, stop, intervals)

        with ThreadPoolExecutor(max_workers=2) as pool:
            tables = dict(pool.map(fetch_table, ("earth", "moon")))

        relative_position = np.subtract(tables["moon"][1][0], tables["earth"][1][0])
        relative_velocity = np.subtract(tables["moon"][2][0], tables["earth"][2][0])
        x_axis = relative_position / np.linalg.norm(relative_position)
        normal = np.cross(relative_position, relative_velocity)
        if np.linalg.norm(normal) == 0.0:
            raise ValueError("No se puede definir el plano orbital inicial.")
        normal /= np.linalg.norm(normal)
        self.basis_icrf = np.stack((x_axis, np.cross(normal, x_axis)))

        basis_t = self.basis_icrf.T
        self.bodies: dict[str, PlanarScenarioBody] = {}
        for key, (times, positions, velocities) in tables.items():
            self.bodies[key] = PlanarScenarioBody(
                catalog[key],
                date,
                times,
                np.asarray(positions) @ basis_t,
                np.asarray(velocities) @ basis_t,
            )

    def get_bodies(self) -> list[ScenarioBody]:
        return list(self.bodies.values())

class SolarPlanarScenario(PlanarScenario):
    """Two selected gravitating bodies, SSB origin, fixed J2000 ecliptic plane."""
    def __init__(self, date, duration_s, origin_id, destination_id, spacing_s=3600):
        from pathlib import Path
        catalog = load_bodies(Path(__file__).with_name("solar_bodies.json"))
        if origin_id == destination_id or origin_id not in catalog or destination_id not in catalog:
            raise ValueError("Elige dos cuerpos distintos del catálogo solar.")
        validate_positive(duration_s, "duration_s")
        self.date, self.duration_s = date, duration_s
        self.origin_id, self.destination_id = origin_id, destination_id
        eps = math.radians(23.439291111)
        self.basis_icrf = np.array([[1., 0., 0.], [0., math.cos(eps), math.sin(eps)]])
        self.bodies = {}
        intervals = min(10000, max(2, math.ceil(duration_s / spacing_s)))
        # Sequential requests respect the public JPL service's usage guidance.
        for key in (origin_id, destination_id):
            times, positions, velocities = ephemeris.get_body_state_table(
                catalog[key], date, date + timedelta(seconds=duration_s), intervals, center="500@0")
            self.bodies[key] = PlanarScenarioBody(catalog[key], date, times,
                np.asarray(positions) @ self.basis_icrf.T,
                np.asarray(velocities) @ self.basis_icrf.T)
