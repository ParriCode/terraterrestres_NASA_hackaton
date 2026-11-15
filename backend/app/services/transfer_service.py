"""F del documento: Lambert, shooting y trayectoria planar con datos Horizons.

Tiempos en segundos desde scenario.date. Coordenadas del plano orbital inicial
del escenario, origen baricéntrico y z=0. Se ignoran rotación y otras gravedades.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
import math
import time
from typing import Callable

import numpy as np
from scipy.optimize import least_squares

from app.data.scenarios import PlanarScenario
from app.models.domain import SpacecraftState, Vec3, validate_positive, validate_vec3
from app.physics.lambert import LambertError, solve_lambert
from app.physics.propagation import propagate_planar
from app.physics.shooting import ShootingResult, solve_shooting

_DEFAULT_PROPAGATE_PLANAR = propagate_planar
_DEFAULT_SOLVE_SHOOTING = solve_shooting

# Coeficientes Dormand-Prince RK5(4) para propagación rápida durante shooting
_DP_A21 = 1.0 / 5.0
_DP_A31 = 3.0 / 40.0
_DP_A32 = 9.0 / 40.0
_DP_A41 = 44.0 / 45.0
_DP_A42 = -56.0 / 15.0
_DP_A43 = 32.0 / 9.0
_DP_A51 = 19372.0 / 6561.0
_DP_A52 = -25360.0 / 2187.0
_DP_A53 = 64448.0 / 6561.0
_DP_A54 = -212.0 / 729.0
_DP_A61 = 9017.0 / 3168.0
_DP_A62 = -355.0 / 33.0
_DP_A63 = 46732.0 / 5247.0
_DP_A64 = 49.0 / 176.0
_DP_A65 = -5103.0 / 18656.0

_DP_B1 = 35.0 / 384.0
_DP_B3 = 500.0 / 1113.0
_DP_B4 = 125.0 / 192.0
_DP_B5 = -2187.0 / 6784.0
_DP_B6 = 11.0 / 84.0

_DP_E1 = 35.0 / 384.0 - 5179.0 / 57600.0
_DP_E3 = 500.0 / 1113.0 - 7571.0 / 16695.0
_DP_E4 = 125.0 / 192.0 - 393.0 / 640.0
_DP_E5 = -2187.0 / 6784.0 - (-92097.0 / 339200.0)
_DP_E6 = 11.0 / 84.0 - 187.0 / 2100.0
_DP_E7 = -1.0 / 40.0

_DP_C2 = 1.0 / 5.0
_DP_C3 = 3.0 / 10.0
_DP_C4 = 4.0 / 5.0
_DP_C5 = 8.0 / 9.0


class TransferNotFoundError(RuntimeError):
    """Ninguna semilla produjo una transferencia válida."""


@dataclass(frozen=True)
class TransferResult:
    scenario: PlanarScenario
    t0_s: float
    t1_s: float
    initial_velocity_m_s: Vec3
    launch_speed_m_s: float
    launch_energy_j: float
    path_length_m: float
    arrival_error_m: float
    mass_kg: float
    objective: str
    launch_delta_v_m_s: float
    arrival_v_infinity_m_s: float
    arrival_delta_v_m_s: float
    total_delta_v_m_s: float
    parking_alt_m: float = 0.0
    _solution: object = field(repr=False, default=None)

    def state(self, time_s: float) -> SpacecraftState:
        """Estado interpolado sin reintegrar, dentro del intervalo del vuelo."""
        if not math.isfinite(time_s) or not self.t0_s <= time_s <= self.t1_s:
            raise ValueError("Tiempo fuera del intervalo de la transferencia.")
        x, y, vx, vy = self._solution.sol(time_s)
        return SpacecraftState((float(x), float(y), 0.0), (float(vx), float(vy), 0.0))

    def pos(self, time_s: float) -> Vec3:
        return self.state(time_s).position_m

    def speed(self, time_s: float) -> Vec3:
        """Vector velocidad en m/s, en los ejes fijos del escenario."""
        return self.state(time_s).velocity_m_s

    def C(self, time_s: float) -> tuple[Vec3, Vec3]:
        state = self.state(time_s)
        return state.position_m, state.velocity_m_s

    def energy(self, time_s: float) -> dict[str, float]:
        """Energía baricéntrica; no es constante con potenciales móviles."""
        state = self.state(time_s)
        rx, ry, rz = state.position_m
        vx, vy, vz = state.velocity_m_s
        kinetic = 0.5 * self.mass_kg * (vx * vx + vy * vy + vz * vz)
        potential = 0.0
        for body in self.scenario.get_bodies():
            bx, by, bz = body.pos(time_s)
            dist = math.hypot(rx - bx, ry - by, rz - bz)
            potential -= self.mass_kg * body.mu_m3_s2 / dist
        return {
            "kinetic_j": float(kinetic),
            "potential_j": float(potential),
            "mechanical_j": float(kinetic + potential),
        }


def _build_fast_shooting_residual(
    scenario: PlanarScenario,
    x0: Vec3,
    target: Vec3,
    t0: float,
    t1: float,
    *,
    budget_check: Callable[[], None] | None = None,
    rtol: float = 1e-8,
    atol: float = 1e-5,
) -> Callable[[Vec3], Vec3] | None:
    """Construye un residuo de shooting en Python puro sin overhead de SciPy/NumPy.

    Devuelve None si el escenario no expone tablas Hermite 2D uniformes o si
    `propagate_planar` fue sustituido (p. ej. en pruebas con monkeypatch).
    """
    if propagate_planar is not _DEFAULT_PROPAGATE_PLANAR:
        return None
    bodies_map = getattr(scenario, "bodies", None)
    if not isinstance(bodies_map, dict) or set(bodies_map.keys()) != {"earth", "moon"}:
        return None

    earth = bodies_map["earth"]
    moon = bodies_map["moon"]
    em = getattr(earth, "_motion", None)
    mm = getattr(moon, "_motion", None)
    if em is None or mm is None:
        return None

    mu0 = float(earth.mu_m3_s2)
    mu1 = float(moon.mu_m3_s2)
    r0_sq = (float(earth.radius_m) - 1.0) ** 2
    r1_sq = (0.5 * float(moon.radius_m)) ** 2

    inv_dt0 = em._inv_dt
    max_idx0 = em._n_intervals - 1
    e_c0x, e_c1x, e_c2x, e_c3x = em._c0x, em._c1x, em._c2x, em._c3x
    e_c0y, e_c1y, e_c2y, e_c3y = em._c0y, em._c1y, em._c2y, em._c3y

    inv_dt1 = mm._inv_dt
    max_idx1 = mm._n_intervals - 1
    m_c0x, m_c1x, m_c2x, m_c3x = mm._c0x, mm._c1x, mm._c2x, mm._c3x
    m_c0y, m_c1y, m_c2y, m_c3y = mm._c0y, mm._c1y, mm._c2y, mm._c3y

    x0_0 = float(x0[0])
    x0_1 = float(x0[1])
    tx = float(target[0])
    ty = float(target[1])
    max_step = min(3600.0, (t1 - t0) / 100.0)
    sqrt = math.sqrt

    def accel(t: float, sx: float, sy: float) -> tuple[float, float] | None:
        u0 = t * inv_dt0
        i0 = int(u0)
        if i0 > max_idx0:
            i0 = max_idx0
        elif i0 < 0:
            i0 = 0
        s0 = u0 - i0
        dx0 = sx - (e_c0x[i0] + s0 * (e_c1x[i0] + s0 * (e_c2x[i0] + s0 * e_c3x[i0])))
        dy0 = sy - (e_c0y[i0] + s0 * (e_c1y[i0] + s0 * (e_c2y[i0] + s0 * e_c3y[i0])))
        d0_2 = dx0 * dx0 + dy0 * dy0
        if d0_2 <= r0_sq:
            return None

        u1 = t * inv_dt1
        i1 = int(u1)
        if i1 > max_idx1:
            i1 = max_idx1
        elif i1 < 0:
            i1 = 0
        s1 = u1 - i1
        dx1 = sx - (m_c0x[i1] + s1 * (m_c1x[i1] + s1 * (m_c2x[i1] + s1 * m_c3x[i1])))
        dy1 = sy - (m_c0y[i1] + s1 * (m_c1y[i1] + s1 * (m_c2y[i1] + s1 * m_c3y[i1])))
        d1_2 = dx1 * dx1 + dy1 * dy1
        if d1_2 <= r1_sq:
            return None

        f0 = -mu0 / (d0_2 * sqrt(d0_2))
        f1 = -mu1 / (d1_2 * sqrt(d1_2))
        return f0 * dx0 + f1 * dx1, f0 * dy0 + f1 * dy1

    def residual(velocity: Vec3) -> Vec3:
        if budget_check is not None:
            budget_check()
        t = t0
        x = x0_0
        y = x0_1
        vx = float(velocity[0])
        vy = float(velocity[1])

        a0 = accel(t, x, y)
        if a0 is None:
            return x - tx, y - ty, 0.0
        ax1, ay1 = a0

        sc_x = atol + abs(x) * rtol
        sc_y = atol + abs(y) * rtol
        sc_vx = atol + abs(vx) * rtol
        sc_vy = atol + abs(vy) * rtol
        d0 = 0.5 * sqrt((x / sc_x) ** 2 + (y / sc_y) ** 2 + (vx / sc_vx) ** 2 + (vy / sc_vy) ** 2)
        d1 = 0.5 * sqrt((vx / sc_x) ** 2 + (vy / sc_y) ** 2 + (ax1 / sc_vx) ** 2 + (ay1 / sc_vy) ** 2)
        h = 1e-6 if (d0 < 1e-5 or d1 < 1e-5) else 0.01 * d0 / d1
        if h > max_step:
            h = max_step

        steps = 0
        while t < t1:
            steps += 1
            if budget_check is not None and (steps & 15) == 1:
                budget_check()
            if t + h >= t1:
                h = t1 - t
                last_step = True
            else:
                last_step = False

            while True:
                x2 = x + h * _DP_A21 * vx
                y2 = y + h * _DP_A21 * vy
                vx2 = vx + h * _DP_A21 * ax1
                vy2 = vy + h * _DP_A21 * ay1
                a2 = accel(t + _DP_C2 * h, x2, y2)
                if a2 is None:
                    return x2 - tx, y2 - ty, 0.0
                ax2, ay2 = a2

                x3 = x + h * (_DP_A31 * vx + _DP_A32 * vx2)
                y3 = y + h * (_DP_A31 * vy + _DP_A32 * vy2)
                vx3 = vx + h * (_DP_A31 * ax1 + _DP_A32 * ax2)
                vy3 = vy + h * (_DP_A31 * ay1 + _DP_A32 * ay2)
                a3 = accel(t + _DP_C3 * h, x3, y3)
                if a3 is None:
                    return x3 - tx, y3 - ty, 0.0
                ax3, ay3 = a3

                x4 = x + h * (_DP_A41 * vx + _DP_A42 * vx2 + _DP_A43 * vx3)
                y4 = y + h * (_DP_A41 * vy + _DP_A42 * vy2 + _DP_A43 * vy3)
                vx4 = vx + h * (_DP_A41 * ax1 + _DP_A42 * ax2 + _DP_A43 * ax3)
                vy4 = vy + h * (_DP_A41 * ay1 + _DP_A42 * ay2 + _DP_A43 * ay3)
                a4 = accel(t + _DP_C4 * h, x4, y4)
                if a4 is None:
                    return x4 - tx, y4 - ty, 0.0
                ax4, ay4 = a4

                x5 = x + h * (_DP_A51 * vx + _DP_A52 * vx2 + _DP_A53 * vx3 + _DP_A54 * vx4)
                y5 = y + h * (_DP_A51 * vy + _DP_A52 * vy2 + _DP_A53 * vy3 + _DP_A54 * vy4)
                vx5 = vx + h * (_DP_A51 * ax1 + _DP_A52 * ax2 + _DP_A53 * ax3 + _DP_A54 * ax4)
                vy5 = vy + h * (_DP_A51 * ay1 + _DP_A52 * ay2 + _DP_A53 * ay3 + _DP_A54 * ay4)
                a5 = accel(t + _DP_C5 * h, x5, y5)
                if a5 is None:
                    return x5 - tx, y5 - ty, 0.0
                ax5, ay5 = a5

                x6 = x + h * (_DP_A61 * vx + _DP_A62 * vx2 + _DP_A63 * vx3 + _DP_A64 * vx4 + _DP_A65 * vx5)
                y6 = y + h * (_DP_A61 * vy + _DP_A62 * vy2 + _DP_A63 * vy3 + _DP_A64 * vy4 + _DP_A65 * vy5)
                vx6 = vx + h * (_DP_A61 * ax1 + _DP_A62 * ax2 + _DP_A63 * ax3 + _DP_A64 * ax4 + _DP_A65 * ax5)
                vy6 = vy + h * (_DP_A61 * ay1 + _DP_A62 * ay2 + _DP_A63 * ay3 + _DP_A64 * ay4 + _DP_A65 * ay5)
                t_next = t1 if last_step else t + h
                a6 = accel(t_next, x6, y6)
                if a6 is None:
                    return x6 - tx, y6 - ty, 0.0
                ax6, ay6 = a6

                xn = x + h * (_DP_B1 * vx + _DP_B3 * vx3 + _DP_B4 * vx4 + _DP_B5 * vx5 + _DP_B6 * vx6)
                yn = y + h * (_DP_B1 * vy + _DP_B3 * vy3 + _DP_B4 * vy4 + _DP_B5 * vy5 + _DP_B6 * vy6)
                vxn = vx + h * (_DP_B1 * ax1 + _DP_B3 * ax3 + _DP_B4 * ax4 + _DP_B5 * ax5 + _DP_B6 * ax6)
                vyn = vy + h * (_DP_B1 * ay1 + _DP_B3 * ay3 + _DP_B4 * ay4 + _DP_B5 * ay5 + _DP_B6 * ay6)
                a7 = accel(t_next, xn, yn)
                if a7 is None:
                    return xn - tx, yn - ty, 0.0
                ax7, ay7 = a7

                ex = h * (_DP_E1 * vx + _DP_E3 * vx3 + _DP_E4 * vx4 + _DP_E5 * vx5 + _DP_E6 * vx6 + _DP_E7 * vxn)
                ey = h * (_DP_E1 * vy + _DP_E3 * vy3 + _DP_E4 * vy4 + _DP_E5 * vy5 + _DP_E6 * vy6 + _DP_E7 * vyn)
                evx = h * (_DP_E1 * ax1 + _DP_E3 * ax3 + _DP_E4 * ax4 + _DP_E5 * ax5 + _DP_E6 * ax6 + _DP_E7 * ax7)
                evy = h * (_DP_E1 * ay1 + _DP_E3 * ay3 + _DP_E4 * ay4 + _DP_E5 * ay5 + _DP_E6 * ay6 + _DP_E7 * ay7)

                sx_tol = atol + max(abs(x), abs(xn)) * rtol
                sy_tol = atol + max(abs(y), abs(yn)) * rtol
                svx_tol = atol + max(abs(vx), abs(vxn)) * rtol
                svy_tol = atol + max(abs(vy), abs(vyn)) * rtol

                err = 0.5 * sqrt(
                    (ex / sx_tol) ** 2
                    + (ey / sy_tol) ** 2
                    + (evx / svx_tol) ** 2
                    + (evy / svy_tol) ** 2
                )
                if err <= 1.0:
                    t = t_next
                    x, y, vx, vy = xn, yn, vxn, vyn
                    ax1, ay1 = ax7, ay7
                    factor = 5.0 if err == 0.0 else min(5.0, max(0.2, 0.9 * (err ** -0.2)))
                    h = min(max_step, h * factor)
                    break
                last_step = False
                h *= max(0.1, 0.9 * (err ** -0.2))
                if t + h == t:
                    raise RuntimeError("Paso mínimo alcanzado en propagación rápida.")

        return x - tx, y - ty, 0.0

    return residual


def _solve_planar_shooting_fast(
    guess: Vec3,
    residual_fn: Callable[[Vec3], Vec3],
    *,
    arrival_tolerance_m: float,
    max_evaluations: int,
) -> ShootingResult:
    """Ajuste Levenberg-Marquardt planar con tolerancias coherentes con la física."""
    if solve_shooting is not _DEFAULT_SOLVE_SHOOTING:
        return solve_shooting(
            guess,
            residual_fn,
            planar=True,
            arrival_tolerance_m=arrival_tolerance_m,
            max_evaluations=max_evaluations,
        )

    v_scale = 1_000.0
    r_scale = 1_000.0
    initial = np.array((guess[0] / v_scale, guess[1] / v_scale), dtype=float)

    def normalized_residual(nv: np.ndarray) -> np.ndarray:
        rx, ry, _ = residual_fn((float(nv[0] * v_scale), float(nv[1] * v_scale), 0.0))
        return np.array((rx / r_scale, ry / r_scale), dtype=float)

    optimization = least_squares(
        normalized_residual,
        initial,
        method="lm",
        max_nfev=max_evaluations,
        xtol=1e-8,
        ftol=1e-8,
        gtol=1e-8,
    )
    velocity: Vec3 = (float(optimization.x[0] * v_scale), float(optimization.x[1] * v_scale), 0.0)
    residual = residual_fn(velocity)
    residual_norm = math.hypot(residual[0], residual[1], residual[2])
    return ShootingResult(
        initial_velocity_m_s=velocity,
        arrival_residual_m=residual,
        residual_norm_m=residual_norm,
        converged=bool(residual_norm <= arrival_tolerance_m),
        evaluations=int(optimization.nfev),
        message=str(optimization.message),
    )


def F(
    x0: Vec3,
    x1: Vec3,
    t0: float,
    t1: float,
    objetivo="energia",
    *,
    scenario: PlanarScenario,
    mass_kg=1.0,
    arrival_tolerance_m=1000.0,
    max_shooting_evaluations=200,
    budget_check: Callable[[], None] | None = None,
    warm_start_velocities: tuple[Vec3, ...] = (),
) -> TransferResult:
    """Busca la mejor candidata válida entre semillas Lambert pro/retrógradas.


def prograde_circular_velocity(mu_m3_s2: float, rel_pos_m: np.ndarray) -> np.ndarray:
    """Velocidad circular tangencial prograde (sentido antihorario en XY)."""
    r_mag = float(np.linalg.norm(rel_pos_m))
    u_r = rel_pos_m / r_mag
    u_t = np.array((-u_r[1], u_r[0], 0.0))
    v_circ = float(np.sqrt(mu_m3_s2 / r_mag))
    return v_circ * u_t


def _earth_positions_xy(earth, times: np.ndarray) -> np.ndarray:
    """Evalúa la posición XY de la Tierra vectorizada sobre todo el array de tiempos."""
    motion = getattr(earth, "_motion", None)
    if callable(motion):
        return np.asarray(motion(times))[:, :2]
    return np.array([earth.pos(float(t))[:2] for t in times])


def F(
    x0: Vec3,
    x1: Vec3,
    t0: float,
    t1: float,
    objetivo="energia",
    *,
    scenario: PlanarScenario,
    mass_kg=1.0,
    arrival_tolerance_m=1000.0,
    parking_alt_m: float = 0.0,
    prograde_hint: bool | None = None,
    warm_start_velocity: Vec3 | None = None,
) -> TransferResult:
    """Busca la mejor candidata válida entre semillas Lambert o arranque en caliente."""
    validate_vec3(x0, "x0")
    validate_vec3(x1, "x1")
    validate_positive(mass_kg, "mass_kg")
    validate_positive(arrival_tolerance_m, "arrival_tolerance_m")
    if not np.isfinite(parking_alt_m) or parking_alt_m < 0:
        raise ValueError("parking_alt_m debe ser finito y no negativo.")
    if not 0 <= t0 < t1 <= scenario.duration_s:
        raise ValueError("Se requiere 0 <= t0 < t1 <= duración del escenario.")
    if x0[2] != 0 or x1[2] != 0:
        raise ValueError("F trabaja en 2D: z debe ser cero.")
    if objetivo not in ("energia", "distancia"):
        raise ValueError("objetivo debe ser energia o distancia.")

    earth, moon = scenario.bodies["earth"], scenario.bodies["moon"]
    earth_pos_t0 = earth.pos(t0)
    moon_pos_t1 = moon.pos(t1)
    if (
        abs(math.hypot(x0[0] - earth_pos_t0[0], x0[1] - earth_pos_t0[1], x0[2] - earth_pos_t0[2]) - earth.radius_m) > 1.0
        or abs(math.hypot(x1[0] - moon_pos_t1[0], x1[1] - moon_pos_t1[1], x1[2] - moon_pos_t1[2]) - moon.radius_m) > 1.0
    ):
        raise ValueError("Los extremos deben estar en las superficies terrestre y lunar.")

    evx, evy, evz = earth.speed(t0)
    mvx, mvy, mvz = moon.speed(t1)
    nx = x0[0] - earth_pos_t0[0]
    ny = x0[1] - earth_pos_t0[1]
    n_norm = math.hypot(nx, ny)
    nx /= n_norm
    ny /= n_norm

    rel_r1: Vec3 = (x0[0] - earth_pos_t0[0], x0[1] - earth_pos_t0[1], x0[2] - earth_pos_t0[2])
    rel_r2: Vec3 = (x1[0] - moon_pos_t1[0], x1[1] - moon_pos_t1[1], x1[2] - moon_pos_t1[2])
    tof = t1 - t0
    earth_mu = earth.mu_m3_s2

    valid: list[TransferResult] = []
    reasons: list[str] = []

    body_keys = list(scenario.bodies)
    earth_index = body_keys.index("earth")
    moon_index = body_keys.index("moon")
    length_times: np.ndarray | None = None
    earth_track_xy: np.ndarray | None = None

    fast_residual = _build_fast_shooting_residual(
        scenario, x0, x1, t0, t1, budget_check=budget_check, rtol=1e-8, atol=1e-5,
    )
    if fast_residual is not None:
        residual = fast_residual
    else:
        target_xy = (float(x1[0]), float(x1[1]))

        def residual(velocity: Vec3) -> Vec3:
            if budget_check is not None:
                budget_check()
            solution = propagate_planar(
                scenario, x0, velocity, t0, t1,
                dense_output=False, rtol=1e-8, atol=1e-5, budget_check=budget_check,
            )
            return float(solution.y[0, -1] - target_xy[0]), float(solution.y[1, -1] - target_xy[1]), 0.0

    def evaluate_guess(guess: Vec3, eval_budget: int) -> None:
        nonlocal length_times, earth_track_xy
        if (guess[0] - evx) * nx + (guess[1] - evy) * ny <= 0.0:
            reasons.append("La salida entra en la Tierra")
            return
        shot = _solve_planar_shooting_fast(
            guess,
            residual,
            arrival_tolerance_m=arrival_tolerance_m,
            max_evaluations=eval_budget,
        )
        if not shot.converged:
            reasons.append(f"Error de llegada: {shot.residual_norm_m:.1f} m")
            return
        vx, vy, vz = shot.initial_velocity_m_s
        if (vx - evx) * nx + (vy - evy) * ny <= 0.0:
            reasons.append("La salida entra en la Tierra")
            return
        if any(
            math.hypot(vx - r.initial_velocity_m_s[0], vy - r.initial_velocity_m_s[1], vz - r.initial_velocity_m_s[2]) < 1.0
            for r in valid
        ):
            return

        # Validación final con salida densa completa para C(t) y métricas.
        solution = propagate_planar(
            scenario, x0, shot.initial_velocity_m_s, t0, t1,
            events=True, dense_output=True, rtol=1e-10, atol=1e-7,
            budget_check=budget_check,
        )
        if len(solution.t_events[earth_index]):
            reasons.append("La trayectoria vuelve a tocar la Tierra")
            return
        if any(t < t1 - 60.0 for t in solution.t_events[moon_index]):
            reasons.append("Primer contacto lunar antes de tiempo")
            return

        fx, fy = float(solution.y[0, -1]), float(solution.y[1, -1])
        fvx, fvy = float(solution.y[2, -1]), float(solution.y[3, -1])
        error = math.hypot(fx - x1[0], fy - x1[1], -x1[2])
        if error > arrival_tolerance_m:
            reasons.append("Error de llegada tras validar")
            return
        if (fvx - mvx) * (fx - moon_pos_t1[0]) + (fvy - mvy) * (fy - moon_pos_t1[1]) + (-mvz) * (-moon_pos_t1[2]) >= 0.0:
            reasons.append("La nave no llega desde fuera de la Luna")
            return

        if length_times is None or earth_track_xy is None:
            length_times = np.linspace(t0, t1, 4000)
            earth_pos_array = getattr(earth, "pos_array", None)
            earth_track_xy = (
                earth_pos_array(length_times)[:, :2]
                if callable(earth_pos_array)
                else np.array([earth.pos(float(t))[:2] for t in length_times])
            )

        relative = solution.sol(length_times)[:2].T - earth_track_xy
        diffs = np.diff(relative, axis=0)
        length = float(np.hypot(diffs[:, 0], diffs[:, 1]).sum())
        launch_speed = math.hypot(vx - evx, vy - evy, vz - evz)
        valid.append(
            TransferResult(
                scenario,
                t0,
                t1,
                shot.initial_velocity_m_s,
                launch_speed,
                0.5 * mass_kg * launch_speed * launch_speed,
                length,
                error,
                mass_kg,
                objetivo,
                solution,
            )
        )

    for warm_guess in warm_start_velocities:
        if budget_check is not None:
            budget_check()
        try:
            evaluate_guess(warm_guess, min(max_shooting_evaluations, 25))
        except (RuntimeError, ArithmeticError, ValueError) as error:
            reasons.append(str(error))

    for factors in ((1.0,), (0.98, 1.02)):
        if valid:
            break
        for prograde in (True, False):
            for factor in factors:
                if budget_check is not None:
                    budget_check()
                try:
                    seed = solve_lambert(
                        rel_r1, rel_r2, tof * factor, earth_mu, prograde=prograde,
                    )
                    dvx, dvy, dvz = seed.departure_velocity_m_s
                    guess: Vec3 = (dvx + evx, dvy + evy, dvz + evz)
                    evaluate_guess(guess, max_shooting_evaluations)
                except (LambertError, RuntimeError, ArithmeticError, ValueError) as error:
                    reasons.append(str(error))

    if not valid:
        prograde_seq = (prograde_hint,) if prograde_hint is not None else (True, False)
        factor_groups = ((1.0,),) if prograde_hint is not None else ((1.0,), (0.98, 1.02))
        rel_r1 = tuple(start - earth.pos(t0))
        rel_r2 = tuple(target - earth.pos(t1))
        for factors in factor_groups:
            if valid:
                break
            for prograde in prograde_seq:
                for factor in factors:
                    try:
                        seed = solve_lambert(
                            rel_r1,
                            rel_r2,
                            (t1 - t0) * factor,
                            earth.mu_m3_s2,
                            prograde=prograde,
                        )
                        guess = tuple(np.asarray(seed.departure_velocity_m_s) + earth_velocity)
                        _validate_guess(guess, max_evals=55)
                    except (LambertError, RuntimeError, ArithmeticError, ValueError) as error:
                        reasons.append(str(error))

    if not valid:
        raise TransferNotFoundError(
            "No se encontró transferencia válida: " + "; ".join(sorted(set(reasons)))
        )
    if objetivo == "energia":
        key = lambda r: r.launch_energy_j
    elif objetivo == "distancia":
        key = lambda r: r.path_length_m
    else:
        key = lambda r: r.total_delta_v_m_s
    return min(valid, key=key)


def design_transfer(
    date: datetime,
    duration_s: float,
    *,
    launch_angle_deg=90.0,
    arrival_angle_deg=0.0,
    objective="energia",
    mass_kg=1.0,
    spacing_s=3600.0,
) -> TransferResult:
    """Carga NASA y llama a F. Alfa: desde Tierra→Luna; beta: Luna→Tierra.

    Los ángulos son geométricos del modelo planar, no latitud/longitud.
    """
    if not math.isfinite(launch_angle_deg) or not math.isfinite(arrival_angle_deg):
        raise ValueError("Los ángulos deben ser finitos.")
    if not np.isfinite(parking_alt_m) or parking_alt_m < 0:
        raise ValueError("parking_alt_m debe ser finito y no negativo.")
    scenario = PlanarScenario(date, duration_s, spacing_s=spacing_s)
    earth, moon = scenario.bodies["earth"], scenario.bodies["moon"]

    def surface(body, other, t: float, angle: float) -> Vec3:
        cx, cy, _ = body.pos(t)
        ox, oy, _ = other.pos(t)
        theta = math.atan2(oy - cy, ox - cx) + math.radians(angle)
        r = body.radius_m
        return (cx + r * math.cos(theta), cy + r * math.sin(theta), 0.0)

    return F(
        surface(earth, moon, 0.0, launch_angle_deg),
        surface(moon, earth, duration_s, arrival_angle_deg),
        0.0,
        duration_s,
        objective,
        scenario=scenario,
        mass_kg=mass_kg,
    )


@dataclass(frozen=True)
class OptimizedTransfer:
    """Mejor candidata *evaluada* en una búsqueda angular finita."""

    transfer: TransferResult
    arrival_angle_deg: float
    attempted_angles_deg: tuple[float, ...]
    valid_candidates: int
    search_complete: bool
    timed_out_angles_deg: tuple[float, ...]


@lru_cache(maxsize=12)
def optimize_transfer(
    date: datetime,
    duration_s: float,
    *,
    launch_angle_deg: float = 90.0,
    objective: str = "energia",
    mass_kg: float = 1.0,
    spacing_s: float = 3600.0,
    time_budget_s: float = 100.0,
    coarse_step_deg: int = 45,
    max_shooting_evaluations: int = 75,
) -> OptimizedTransfer:
    """Busca un ángulo de llegada sin asumir que 0° sea el óptimo.

    Reutiliza en memoria el resultado si se repite exactamente la petición.
    Misma fecha/duración y efemérides para todos los candidatos. En primer
    lugar se evalúa una rejilla circular de ángulos; después se prueban dos
    vecinos del mejor resultado. Se rechazan impactos y fallos de llegada por
    las validaciones existentes de F. El tiempo y la malla son acotados.

    Es el mejor candidato *encontrado*, no un óptimo continuo o global.
    """
    validate_positive(mass_kg, "mass_kg")
    validate_positive(time_budget_s, "time_budget_s")
    validate_positive(duration_s, "duration_s")
    if objective not in ("energia", "distancia"):
        raise ValueError("objective debe ser energia o distancia.")
    if not math.isfinite(launch_angle_deg):
        raise ValueError("launch_angle_deg debe ser finito.")
    if not isinstance(coarse_step_deg, int) or isinstance(coarse_step_deg, bool) or coarse_step_deg <= 0 or 360 % coarse_step_deg:
        raise ValueError("coarse_step_deg debe dividir 360 exactamente.")
    if not isinstance(max_shooting_evaluations, int) or max_shooting_evaluations < 3:
        raise ValueError("max_shooting_evaluations debe ser >= 3.")

    # Sólo una descarga / proyección de efemérides por petición.
    scenario = PlanarScenario(date, duration_s, spacing_s=spacing_s)
    earth, moon = scenario.bodies["earth"], scenario.bodies["moon"]

    ex0, ey0, _ = earth.pos(0.0)
    mx0, my0, _ = moon.pos(0.0)
    theta_launch = math.atan2(my0 - ey0, mx0 - ex0) + math.radians(launch_angle_deg)
    er = earth.radius_m
    start: Vec3 = (ex0 + er * math.cos(theta_launch), ey0 + er * math.sin(theta_launch), 0.0)

    mx1, my1, _ = moon.pos(duration_s)
    ex1, ey1, _ = earth.pos(duration_s)
    base_arrival_theta = math.atan2(ey1 - my1, ex1 - mx1)
    mr = moon.radius_m

    best: TransferResult | None = None
    best_angle: float | None = None
    attempted: list[float] = []
    attempted_set: set[float] = set()
    valid_count = 0
    complete = True
    expires = time.monotonic() + time_budget_s
    skipped_slow: list[float] = []
    is_energy = objective == "energia"

    class SlowCandidate(TimeoutError):
        pass

    def ensure_time_left():
        if time.monotonic() >= expires:
            raise TimeoutError("Se agotó el presupuesto de búsqueda angular.")

    def normalized(degrees: float) -> float:
        angle = (degrees + 180.0) % 360.0 - 180.0
        return 0.0 if angle == 0.0 else float(angle)

    def attempt(angle: float, *, use_warm_start: bool = False):
        nonlocal best, best_angle, valid_count, complete
        angle = normalized(angle)
        if angle in attempted_set:
            return
        ensure_time_left()
        attempted_set.add(angle)
        attempted.append(angle)
        theta = base_arrival_theta + math.radians(angle)
        target: Vec3 = (mx1 + mr * math.cos(theta), my1 + mr * math.sin(theta), 0.0)
        candidate_expires = min(expires, time.monotonic() + 10.0)

        def check_candidate_budget():
            ensure_time_left()
            if time.monotonic() >= candidate_expires:
                raise SlowCandidate("Geometría descartada por superar el tiempo permitido.")

        warm_seeds = (
            (best.initial_velocity_m_s,)
            if (use_warm_start and best is not None and hasattr(best, "initial_velocity_m_s"))
            else ()
        )

        try:
            if warm_seeds:
                result = F(
                    start, target, 0.0, duration_s, objective,
                    scenario=scenario, mass_kg=mass_kg,
                    max_shooting_evaluations=max_shooting_evaluations,
                    budget_check=check_candidate_budget,
                    warm_start_velocities=warm_seeds,
                )
            else:
                result = F(
                    start, target, 0.0, duration_s, objective,
                    scenario=scenario, mass_kg=mass_kg,
                    max_shooting_evaluations=max_shooting_evaluations,
                    budget_check=check_candidate_budget,
                )
        except TransferNotFoundError:
            return
        except SlowCandidate:
            skipped_slow.append(angle)
            complete = False
            return
        except TimeoutError:
            complete = False
            raise
        valid_count += 1
        if best is None or (
            result.launch_energy_j < best.launch_energy_j
            if is_energy
            else result.path_length_m < best.path_length_m
        ):
            best, best_angle = result, angle

    # Rejilla simétrica que incluye 0° como candidato, sin privilegiarlo.
    try:
        angles = sorted(range(-180, 180, coarse_step_deg), key=lambda a: (abs(a), a))
        for angle in angles:
            attempt(float(angle))
        if best_angle is not None:
            for offset in (-coarse_step_deg / 3.0, coarse_step_deg / 3.0):
                attempt(best_angle + offset, use_warm_start=True)
    except TimeoutError:
        complete = False

    if best is None or best_angle is None:
        suffix = " (tiempo agotado)" if not complete else ""
        raise TransferNotFoundError(
            f"No se encontró una transferencia Tierra–Luna válida para la fecha y duración "
            f"indicadas, tras evaluar {len(attempted)} ángulos{suffix}."
        )
    return OptimizedTransfer(
        best, best_angle, tuple(attempted), valid_count, complete, tuple(skipped_slow),
    )