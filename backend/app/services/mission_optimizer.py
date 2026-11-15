"""Optimización de transferencias Tierra→Luna e ida y vuelta Tierra→Luna→Tierra."""

from dataclasses import dataclass, field
from datetime import datetime
import math
from typing import Literal, Sequence

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq, least_squares, minimize_scalar

from app.mission.data.scenarios import PlanarScenario, SpatialScenario
from app.mission.models.domain import SpacecraftState, Vec3
from app.mission.physics.lambert import LambertError, solve_lambert
from app.mission.services.transfer_service import (
    F,
    TransferNotFoundError,
    TransferResult,
    orbit_point,
    prograde_circular_velocity,
)

DEFAULT_PARKING_ALT_M = 200_000.0
DEFAULT_MIN_DURATION_S = 2.5 * 86400.0
DEFAULT_DURATION_STEP_S = 0.5 * 86400.0
DEFAULT_LAUNCH_ANGLES_DEG: tuple[float, ...] = tuple(float(a) for a in range(0, 360, 20))
DEFAULT_ARRIVAL_ANGLES_DEG: tuple[float, ...] = tuple(float(a) for a in range(0, 360, 60))


@dataclass(frozen=True)
class Candidate:
    duration_s: float
    launch_angle_deg: float
    arrival_angle_deg: float
    prograde: bool
    estimated_launch_delta_v_m_s: float
    estimated_v_infinity_m_s: float
    estimated_arrival_delta_v_m_s: float
    estimated_total_delta_v_m_s: float


@dataclass(frozen=True)
class TradeoffPoint:
    duration_s: float
    estimated_launch_delta_v_m_s: float
    estimated_arrival_delta_v_m_s: float
    estimated_total_delta_v_m_s: float
    launch_angle_deg: float
    arrival_angle_deg: float
    prograde: bool


@dataclass(frozen=True)
class OptimizationResult:
    transfer: TransferResult
    best_candidate: Candidate
    tradeoff: list[TradeoffPoint]
    min_duration_s: float
    max_duration_s: float
    candidates_evaluated: int
    propagations_run: int


@dataclass(frozen=True)
class RoundTripResult:
    """Trayectoria 3D completa Tierra → Luna → Tierra."""

    scenario: SpatialScenario
    mode: Literal["free_return", "lunar_orbit"]
    outbound_duration_s: float
    lunar_stay_s: float
    inbound_duration_s: float
    total_duration_s: float
    tli_delta_v_m_s: float
    loi_delta_v_m_s: float
    tei_delta_v_m_s: float
    total_delta_v_m_s: float
    min_lunar_altitude_m: float
    earth_reentry_altitude_m: float
    mass_kg: float
    _segments: tuple[tuple[float, float, object], ...] = field(repr=False, default=())

    def state(self, time_s: float) -> SpacecraftState:
        if not np.isfinite(time_s) or not 0.0 <= time_s <= self.total_duration_s + 1e-6:
            raise ValueError("Tiempo fuera del intervalo de la misión de retorno.")
        t_clamped = float(np.clip(time_s, 0.0, self.total_duration_s))
        for t_start, t_end, sol in self._segments:
            if t_start - 1e-6 <= t_clamped <= t_end + 1e-6:
                y = sol.sol(float(np.clip(t_clamped, t_start, t_end)))
                return SpacecraftState(
                    (float(y[0]), float(y[1]), float(y[2])),
                    (float(y[3]), float(y[4]), float(y[5])),
                )
        raise ValueError("Segmento temporal no encontrado en RoundTripResult.")

    def pos(self, time_s: float) -> Vec3:
        return self.state(time_s).position_m

    def speed(self, time_s: float) -> Vec3:
        return self.state(time_s).velocity_m_s


class NoFeasibleTransfer(RuntimeError):
    """No se encontró ninguna transferencia viable dentro de las restricciones dadas."""

    def __init__(
        self,
        reasons: Sequence[str],
        tradeoff: Sequence[TradeoffPoint] = (),
        *,
        min_duration_s: float = DEFAULT_MIN_DURATION_S,
        max_duration_s: float = 0.0,
    ):
        self.reasons = list(dict.fromkeys(reasons))
        self.tradeoff = list(tradeoff)
        self.min_duration_s = float(min_duration_s)
        self.max_duration_s = float(max_duration_s)
        super().__init__(
            "; ".join(self.reasons) if self.reasons else "No se encontró transferencia factible."
        )


def _angle_diff_deg(a: float, b: float) -> float:
    return abs(((a - b + 180.0) % 360.0) - 180.0)


def _duration_grid(min_duration_s: float, max_duration_s: float, step_s: float) -> list[float]:
    if max_duration_s < min_duration_s:
        return []
    durations: list[float] = []
    t = float(min_duration_s)
    while t <= max_duration_s + 1e-6:
        durations.append(min(t, float(max_duration_s)))
        t += step_s
    if durations and abs(durations[-1] - max_duration_s) > 1.0:
        durations.append(float(max_duration_s))
    return durations


def _lambert_periapsis_m(r1: np.ndarray, v1: np.ndarray, mu_earth: float) -> float:
    r_mag = float(np.linalg.norm(r1))
    v_sq = float(np.dot(v1, v1))
    h_vec = np.cross(r1, v1)
    h_sq = float(np.dot(h_vec, h_vec))
    ecc_vec = ((v_sq - mu_earth / r_mag) * r1 - float(np.dot(r1, v1)) * v1) / mu_earth
    ecc = float(np.linalg.norm(ecc_vec))
    return float(h_sq / (mu_earth * (1.0 + ecc)))


def screen(
    scenario: PlanarScenario,
    *,
    parking_alt_m: float = DEFAULT_PARKING_ALT_M,
    min_duration_s: float = DEFAULT_MIN_DURATION_S,
    max_duration_s: float | None = None,
    duration_step_s: float = DEFAULT_DURATION_STEP_S,
    launch_angles_deg: Sequence[float] = DEFAULT_LAUNCH_ANGLES_DEG,
    arrival_angles_deg: Sequence[float] = DEFAULT_ARRIVAL_ANGLES_DEG,
    prograde_options: Sequence[bool] = (True, False),
) -> list[Candidate]:
    """Criba candidatos usando Lambert de dos cuerpos respecto a la Tierra."""
    if not np.isfinite(parking_alt_m) or parking_alt_m < 0:
        raise ValueError("parking_alt_m debe ser finito y no negativo.")
    if not np.isfinite(min_duration_s) or min_duration_s <= 0:
        raise ValueError("min_duration_s debe ser positivo.")
    if not np.isfinite(duration_step_s) or duration_step_s <= 0:
        raise ValueError("duration_step_s debe ser positivo.")

    upper_s = float(
        scenario.duration_s if max_duration_s is None else min(max_duration_s, scenario.duration_s)
    )
    durations = _duration_grid(min_duration_s, upper_s, duration_step_s)
    if not durations:
        return []

    earth = scenario.bodies["earth"]
    moon = scenario.bodies["moon"]
    earth_pos_0 = np.asarray(earth.pos(0.0))
    v_esc_moon = float(np.sqrt(2.0 * moon.mu_m3_s2 / moon.radius_m))

    launch_points: list[tuple[float, np.ndarray, tuple[float, float, float], np.ndarray]] = []
    for alpha in launch_angles_deg:
        p0 = np.asarray(orbit_point(earth, moon, 0.0, alpha, parking_alt_m))
        r1 = p0 - earth_pos_0
        v_circ = prograde_circular_velocity(earth.mu_m3_s2, r1)
        launch_points.append((float(alpha), r1, (float(r1[0]), float(r1[1]), 0.0), v_circ))

    candidates: list[Candidate] = []
    for duration_s in durations:
        earth_pos_t1 = np.asarray(earth.pos(duration_s))
        earth_vel_t1 = np.asarray(earth.speed(duration_s))
        moon_pos_t1 = np.asarray(moon.pos(duration_s))
        moon_vel_t1 = np.asarray(moon.speed(duration_s))

        arrival_points = [
            (float(beta), np.asarray(orbit_point(moon, earth, duration_s, beta, 0.0)))
            for beta in arrival_angles_deg
        ]

        for alpha, r1, r1_tuple, v_circ in launch_points:
            for beta, p1 in arrival_points:
                r2 = p1 - earth_pos_t1
                r2_tuple = (float(r2[0]), float(r2[1]), 0.0)
                r_moon_surf = p1 - moon_pos_t1
                for prograde in prograde_options:
                    try:
                        seed = solve_lambert(
                            r1_tuple, r2_tuple, duration_s, earth.mu_m3_s2, prograde=prograde
                        )
                    except (LambertError, ValueError, ArithmeticError):
                        continue
                    v_dep_rel = np.asarray(seed.departure_velocity_m_s)
                    if float(np.dot(r1, v_dep_rel)) < -1.0:
                        if _lambert_periapsis_m(r1, v_dep_rel, earth.mu_m3_s2) < earth.radius_m:
                            continue
                    v_arr_bary = earth_vel_t1 + np.asarray(seed.arrival_velocity_m_s)
                    v_inf_vec = v_arr_bary - moon_vel_t1
                    if float(np.dot(v_inf_vec, r_moon_surf)) >= 0.0:
                        continue

                    launch_dv = float(np.linalg.norm(v_dep_rel - v_circ))
                    v_inf = float(np.linalg.norm(v_inf_vec))
                    arrival_dv = float(np.hypot(v_inf, v_esc_moon))
                    total_dv = float(launch_dv + arrival_dv)
                    candidates.append(
                        Candidate(
                            duration_s=float(duration_s),
                            launch_angle_deg=alpha,
                            arrival_angle_deg=beta,
                            prograde=bool(prograde),
                            estimated_launch_delta_v_m_s=launch_dv,
                            estimated_v_infinity_m_s=v_inf,
                            estimated_arrival_delta_v_m_s=arrival_dv,
                            estimated_total_delta_v_m_s=total_dv,
                        )
                    )

    candidates.sort(key=lambda c: c.estimated_total_delta_v_m_s)
    return candidates


def build_tradeoff_curve(candidates: Sequence[Candidate]) -> list[TradeoffPoint]:
    """Extrae el mejor Δv estimado por cada tiempo de vuelo del cribado."""
    best_by_duration: dict[float, Candidate] = {}
    for cand in candidates:
        existing = best_by_duration.get(cand.duration_s)
        if existing is None or cand.estimated_total_delta_v_m_s < existing.estimated_total_delta_v_m_s:
            best_by_duration[cand.duration_s] = cand
    return [
        TradeoffPoint(
            duration_s=c.duration_s,
            estimated_launch_delta_v_m_s=c.estimated_launch_delta_v_m_s,
            estimated_arrival_delta_v_m_s=c.estimated_arrival_delta_v_m_s,
            estimated_total_delta_v_m_s=c.estimated_total_delta_v_m_s,
            launch_angle_deg=c.launch_angle_deg,
            arrival_angle_deg=c.arrival_angle_deg,
            prograde=c.prograde,
        )
        for c in (best_by_duration[d] for d in sorted(best_by_duration))
    ]


def deduplicate_candidates(
    candidates: Sequence[Candidate],
    *,
    limit: int = 8,
    duration_tol_s: float = 0.5 * 86400.0 + 1.0,
    launch_angle_tol_deg: float = 25.0,
    arrival_angle_tol_deg: float = 65.0,
) -> list[Candidate]:
    """Selecciona los mejores candidatos evitando agrupar propagaciones en la misma cuenca."""
    selected: list[Candidate] = []
    for cand in candidates:
        if any(
            abs(cand.duration_s - s.duration_s) <= duration_tol_s
            and _angle_diff_deg(cand.launch_angle_deg, s.launch_angle_deg) <= launch_angle_tol_deg
            and _angle_diff_deg(cand.arrival_angle_deg, s.arrival_angle_deg) <= arrival_angle_tol_deg
            for s in selected
        ):
            continue
        selected.append(cand)
        if len(selected) >= limit:
            break
    return selected


def _evaluate_candidate(
    scenario: PlanarScenario,
    duration_s: float,
    launch_angle_deg: float,
    arrival_angle_deg: float,
    *,
    parking_alt_m: float,
    mass_kg: float,
    prograde_hint: bool | None = None,
    warm_start_velocity: Vec3 | None = None,
) -> TransferResult:
    earth, moon = scenario.bodies["earth"], scenario.bodies["moon"]
    return F(
        orbit_point(earth, moon, 0.0, launch_angle_deg, parking_alt_m),
        orbit_point(moon, earth, duration_s, arrival_angle_deg, 0.0),
        0.0,
        duration_s,
        "delta_v",
        scenario=scenario,
        mass_kg=mass_kg,
        parking_alt_m=parking_alt_m,
        prograde_hint=prograde_hint,
        warm_start_velocity=warm_start_velocity,
    )


def refine_local(
    scenario: PlanarScenario,
    initial_result: TransferResult,
    initial_candidate: Candidate,
    *,
    parking_alt_m: float,
    min_duration_s: float,
    max_duration_s: float,
    mass_kg: float = 1.0,
) -> tuple[TransferResult, Candidate, int]:
    """Refinamiento local con arranque en caliente sobre (duración, α, β)."""
    best_result = initial_result
    best_duration = initial_candidate.duration_s
    best_alpha = initial_candidate.launch_angle_deg
    best_beta = initial_candidate.arrival_angle_deg
    evaluations = 0

    for dt_step, dalpha_step, dbeta_step in ((0.25 * 86400.0, 6.0, 20.0),):
        neighbors = (
            (max(min_duration_s, best_duration - dt_step), best_alpha, best_beta),
            (min(max_duration_s, best_duration + dt_step), best_alpha, best_beta),
            (best_duration, (best_alpha - dalpha_step) % 360.0, best_beta),
            (best_duration, (best_alpha + dalpha_step) % 360.0, best_beta),
            (best_duration, best_alpha, (best_beta - dbeta_step) % 360.0),
            (best_duration, best_alpha, (best_beta + dbeta_step) % 360.0),
        )
        seen: set[tuple[float, float, float]] = set()
        for dur, alpha, beta in neighbors:
            key = (round(dur, 3), round(alpha, 3), round(beta, 3))
            if key in seen or (
                abs(dur - best_duration) < 1.0
                and _angle_diff_deg(alpha, best_alpha) < 1e-3
                and _angle_diff_deg(beta, best_beta) < 1e-3
            ):
                continue
            seen.add(key)
            evaluations += 1
            try:
                candidate_res = _evaluate_candidate(
                    scenario,
                    dur,
                    alpha,
                    beta,
                    parking_alt_m=parking_alt_m,
                    mass_kg=mass_kg,
                    prograde_hint=initial_candidate.prograde,
                    warm_start_velocity=best_result.initial_velocity_m_s,
                )
            except (TransferNotFoundError, LambertError, ValueError, RuntimeError):
                continue
            if candidate_res.total_delta_v_m_s < best_result.total_delta_v_m_s:
                best_result = candidate_res
                best_duration = dur
                best_alpha = alpha
                best_beta = beta

    refined_candidate = Candidate(
        duration_s=best_duration,
        launch_angle_deg=best_alpha,
        arrival_angle_deg=best_beta,
        prograde=initial_candidate.prograde,
        estimated_launch_delta_v_m_s=best_result.launch_delta_v_m_s,
        estimated_v_infinity_m_s=best_result.arrival_v_infinity_m_s,
        estimated_arrival_delta_v_m_s=best_result.arrival_delta_v_m_s,
        estimated_total_delta_v_m_s=best_result.total_delta_v_m_s,
    )
    return best_result, refined_candidate, evaluations


def optimize_transfer(
    date: datetime,
    max_duration_s: float,
    *,
    parking_alt_m: float = DEFAULT_PARKING_ALT_M,
    min_duration_s: float = DEFAULT_MIN_DURATION_S,
    duration_step_s: float = DEFAULT_DURATION_STEP_S,
    spacing_s: float = 3600.0,
    top_k: int = 4,
    mass_kg: float = 1.0,
    refine: bool = True,
) -> OptimizationResult:
    """Optimiza Δv total estimado Tierra→Luna sujeto a tiempo máximo de vuelo."""
    if not np.isfinite(max_duration_s) or max_duration_s <= 0:
        raise ValueError("max_duration_s debe ser positivo y finito.")
    if not np.isfinite(parking_alt_m) or parking_alt_m < 0:
        raise ValueError("parking_alt_m debe ser finito y no negativo.")
    if not np.isfinite(min_duration_s) or min_duration_s <= 0:
        raise ValueError("min_duration_s debe ser positivo y finito.")

    if max_duration_s < min_duration_s:
        raise NoFeasibleTransfer(
            [
                f"El tiempo máximo solicitado ({max_duration_s / 86400:.2f} días) es inferior "
                f"al dominio mínimo de búsqueda ({min_duration_s / 86400:.2f} días)."
            ],
            [],
            min_duration_s=min_duration_s,
            max_duration_s=max_duration_s,
        )

    scenario = PlanarScenario(date, max_duration_s, spacing_s=spacing_s)
    candidates = screen(
        scenario,
        parking_alt_m=parking_alt_m,
        min_duration_s=min_duration_s,
        max_duration_s=max_duration_s,
        duration_step_s=duration_step_s,
    )
    tradeoff = build_tradeoff_curve(candidates)
    if not candidates:
        raise NoFeasibleTransfer(
            ["El cribado Lambert no encontró geometrías válidas dentro del intervalo explorado."],
            tradeoff,
            min_duration_s=min_duration_s,
            max_duration_s=max_duration_s,
        )

    direct_pool = [c for c in candidates if c.duration_s <= 6.5 * 86400.0]
    shortlist = deduplicate_candidates(direct_pool, limit=3)
    for cand in deduplicate_candidates(candidates, limit=top_k):
        if cand not in shortlist:
            shortlist.append(cand)
        if len(shortlist) >= top_k:
            break

    validated: list[tuple[TransferResult, Candidate]] = []
    reasons: list[str] = []
    propagations_run = 0

    def try_candidates(pool: Sequence[Candidate]) -> None:
        nonlocal propagations_run
        for cand in pool:
            propagations_run += 1
            try:
                res = _evaluate_candidate(
                    scenario,
                    cand.duration_s,
                    cand.launch_angle_deg,
                    cand.arrival_angle_deg,
                    parking_alt_m=parking_alt_m,
                    mass_kg=mass_kg,
                    prograde_hint=cand.prograde,
                )
                validated.append((res, cand))
                break
            except (TransferNotFoundError, LambertError, ValueError, RuntimeError) as error:
                reasons.append(str(error))

    try_candidates(shortlist)
    if not validated:
        fallback = [c for c in (direct_pool[:6] + candidates[:6]) if c not in shortlist]
        try_candidates(fallback[:5])

    if not validated:
        raise NoFeasibleTransfer(
            reasons or ["Ningún candidato superó la propagación completa DOP853."],
            tradeoff,
            min_duration_s=min_duration_s,
            max_duration_s=max_duration_s,
        )

    best_result, best_cand = min(validated, key=lambda pair: pair[0].total_delta_v_m_s)
    if refine:
        best_result, best_cand, refine_evals = refine_local(
            scenario,
            best_result,
            best_cand,
            parking_alt_m=parking_alt_m,
            min_duration_s=min_duration_s,
            max_duration_s=max_duration_s,
            mass_kg=mass_kg,
        )
        propagations_run += refine_evals

    return OptimizationResult(
        transfer=best_result,
        best_candidate=best_cand,
        tradeoff=tradeoff,
        min_duration_s=float(min_duration_s),
        max_duration_s=float(max_duration_s),
        candidates_evaluated=len(candidates),
        propagations_run=propagations_run,
    )


# ---------------------------------------------------------------------------
# Trayectorias 3D de ida y vuelta: Tierra → Luna → Tierra sin tocar la Luna
# ---------------------------------------------------------------------------


def _build_fast_rhs_3d(bodies: tuple, *, softened: bool = False):
    """Construye una función RHS 3D rápida preextrayendo los interpoladores _motion."""
    motions = [
        (
            body.id,
            float(body.mu_m3_s2),
            (0.4 * float(body.radius_m)) ** 2,
            getattr(body, "_motion", None),
            body,
        )
        for body in bodies
    ]

    def rhs(t_s: float, y: np.ndarray):
        rx, ry, rz = float(y[0]), float(y[1]), float(y[2])
        ax = ay = az = 0.0
        for body_id, mu, soft_sq, motion, body in motions:
            bx, by, bz = motion(t_s) if callable(motion) else body.pos(t_s)
            dx, dy, dz = bx - rx, by - ry, bz - rz
            dist_sq = dx * dx + dy * dy + dz * dz
            if softened and body_id in ("earth", "moon") and dist_sq < soft_sq:
                dist_sq = soft_sq
            elif dist_sq == 0.0:
                continue
            inv_dist3 = mu / (dist_sq * math.sqrt(dist_sq))
            ax += dx * inv_dist3
            ay += dy * inv_dist3
            az += dz * inv_dist3
            if body_id == "sun":
                norm_b_sq = bx * bx + by * by + bz * bz
                if norm_b_sq > 0.0:
                    indirect = mu / (norm_b_sq * math.sqrt(norm_b_sq))
                    ax -= bx * indirect
                    ay -= by * indirect
                    az -= bz * indirect
        return (float(y[3]), float(y[4]), float(y[5]), ax, ay, az)

    return rhs


def _propagate_3d(
    bodies: tuple,
    y0: np.ndarray,
    t0: float,
    t1: float,
    *,
    rtol: float = 1e-8,
    atol: float = 1e-8,
    dense_output: bool = True,
    strict_impact: bool = True,
    reentry_radius_m: float | None = None,
    reentry_after_s: float = 0.0,
    max_step: float = np.inf,
):
    """Propaga en 3D con DOP853 y detección continua de impacto o reentrada."""
    events = []
    earth_body = next(b for b in bodies if b.id == "earth")
    moon_body = next(b for b in bodies if b.id == "moon")
    earth_motion = getattr(earth_body, "_motion", None)
    moon_motion = getattr(moon_body, "_motion", None)

    if strict_impact:
        r_moon = float(moon_body.radius_m)
        r_earth = float(earth_body.radius_m)

        def moon_impact(t, y):
            bx, by, bz = moon_motion(t) if callable(moon_motion) else moon_body.pos(t)
            return math.hypot(y[0] - bx, y[1] - by, y[2] - bz) - r_moon

        moon_impact.terminal = True
        moon_impact.direction = -1
        events.append(moon_impact)

        def earth_impact(t, y):
            bx, by, bz = earth_motion(t) if callable(earth_motion) else earth_body.pos(t)
            return math.hypot(y[0] - bx, y[1] - by, y[2] - bz) - r_earth

        earth_impact.terminal = True
        earth_impact.direction = -1
        events.append(earth_impact)

    if reentry_radius_m is not None:
        r_re = float(reentry_radius_m)
        t_min = float(reentry_after_s)

        def reentry_event(t, y):
            if t < t_min:
                return 1e8
            bx, by, bz = earth_motion(t) if callable(earth_motion) else earth_body.pos(t)
            return math.hypot(y[0] - bx, y[1] - by, y[2] - bz) - r_re

        reentry_event.terminal = True
        reentry_event.direction = -1
        events.append(reentry_event)

    rhs = _build_fast_rhs_3d(bodies, softened=not strict_impact)
    solution = solve_ivp(
        rhs,
        (float(t0), float(t1)),
        np.asarray(y0, dtype=np.float64),
        method="DOP853",
        rtol=rtol,
        atol=atol,
        dense_output=dense_output,
        events=events or None,
        max_step=max_step,
    )

    # Verificación continua por cuerda para no perder reentradas rápidas dentro de un paso
    if (
        reentry_radius_m is not None
        and solution.success
        and solution.sol is not None
        and len(solution.t) >= 2
        and (solution.t_events is None or len(solution.t_events) < 3 or len(solution.t_events[2]) == 0)
    ):
        ts = solution.t
        mask = ts >= float(reentry_after_s)
        if np.count_nonzero(mask) >= 2:
            ts_sub = ts[mask]
            sc_sub = solution.y[:3, mask].T
            centers = (
                np.asarray(earth_motion(ts_sub))
                if callable(earth_motion)
                else np.asarray([earth_body.pos(float(t)) for t in ts_sub])
            )
            rel = sc_sub - centers
            delta = np.diff(rel, axis=0)
            denom = np.sum(delta * delta, axis=1)
            alpha = np.clip(-np.sum(rel[:-1] * delta, axis=1) / np.maximum(denom, 1e-30), 0.0, 1.0)
            chord = rel[:-1] + alpha[:, None] * delta
            r_re = float(reentry_radius_m)
            for j in np.flatnonzero(np.sum(chord * chord, axis=1) <= r_re**2):
                left, right = float(ts_sub[j]), float(ts_sub[j + 1])

                def clearance(t):
                    bx, by, bz = earth_motion(t) if callable(earth_motion) else earth_body.pos(t)
                    p = solution.sol(t)[:3]
                    return math.hypot(p[0] - bx, p[1] - by, p[2] - bz) - r_re

                if clearance(left) <= 0.0:
                    continue
                minimum = minimize_scalar(
                    clearance, bounds=(left, right), method="bounded", options={"xatol": 1e-4, "maxiter": 30}
                )
                if minimum.fun <= 0.0:
                    hit = float(brentq(clearance, left, float(minimum.x), xtol=1e-5))
                    hit_state = np.asarray(solution.sol(hit), dtype=np.float64)
                    idx_cut = int(np.searchsorted(solution.t, hit))
                    solution.t = np.concatenate((solution.t[:idx_cut], [hit]))
                    solution.y = np.column_stack((solution.y[:, :idx_cut], hit_state))
                    if solution.t_events is not None and len(solution.t_events) >= 3:
                        solution.t_events[2] = np.array([hit])
                    break

    if strict_impact and solution.t_events is not None:
        if len(solution.t_events[0]) > 0 or len(solution.t_events[1]) > 0:
            solution.success = False
            solution.message = "La trayectoria impactó Tierra o Luna."
    return solution


def _orbital_basis(earth, moon, t_s: float = 0.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Base ortonormal (u_em, u_perp, u_h) del plano instantáneo Tierra-Luna."""
    rel_m = np.asarray(moon.pos(t_s), dtype=np.float64) - np.asarray(earth.pos(t_s), dtype=np.float64)
    rel_v = np.asarray(moon.speed(t_s), dtype=np.float64) - np.asarray(earth.speed(t_s), dtype=np.float64)
    u_em = rel_m / np.linalg.norm(rel_m)
    h_vec = np.cross(rel_m, rel_v)
    u_h = h_vec / np.linalg.norm(h_vec)
    u_perp = np.cross(u_h, u_em)
    return u_em, u_perp, u_h


def _aligned_launch_angles(earth, moon, t_out: float, offsets_deg: Sequence[float]) -> list[float]:
    """Calcula ángulos de salida en LEO alineados con la posición lunar en t_out."""
    u_em0, u_perp0, _ = _orbital_basis(earth, moon, 0.0)
    rel_m_t1 = np.asarray(moon.pos(t_out), dtype=np.float64) - np.asarray(earth.pos(t_out), dtype=np.float64)
    phi_moon = np.rad2deg(np.arctan2(np.dot(rel_m_t1, u_perp0), np.dot(rel_m_t1, u_em0)))
    base_alpha = (phi_moon + 180.0) % 360.0
    return [float((base_alpha + d) % 360.0) for d in offsets_deg]


def _parking_state_3d(
    earth,
    moon,
    alpha_deg: float,
    parking_alt_m: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Posición y velocidad inercial en la órbita circular de aparcamiento terrestre."""
    e_pos = np.asarray(earth.pos(0.0), dtype=np.float64)
    e_vel = np.asarray(earth.speed(0.0), dtype=np.float64)
    u_em, u_perp, _ = _orbital_basis(earth, moon, 0.0)

    rad = np.deg2rad(alpha_deg)
    u_r = np.cos(rad) * u_em + np.sin(rad) * u_perp
    u_t = -np.sin(rad) * u_em + np.cos(rad) * u_perp

    r_park = earth.radius_m + parking_alt_m
    v_circ = float(np.sqrt(earth.mu_m3_s2 / r_park))
    pos_0 = e_pos + r_park * u_r
    vel_0 = e_vel + v_circ * u_t
    return pos_0, vel_0


def _lambert_plane_normal(r1: np.ndarray, r2: np.ndarray, fallback: np.ndarray) -> Vec3:
    """Normal del plano 3D definido por los vectores geocéntricos de salida y llegada."""
    cross = np.cross(r1, r2)
    norm = float(np.linalg.norm(cross))
    if norm <= 1e-6:
        return (float(fallback[0]), float(fallback[1]), float(fallback[2]))
    if float(np.dot(cross, fallback)) < 0.0:
        cross = -cross
    unit = cross / norm
    return (float(unit[0]), float(unit[1]), float(unit[2]))


def _shoot_3d_target(
    bodies: tuple,
    r0: np.ndarray,
    v0_guess: np.ndarray,
    t0: float,
    t1: float,
    target_pos_fn,
    *,
    tol_m: float = 20_000.0,
) -> tuple[bool, np.ndarray, object]:
    """Ajusta v0 en 3D con diff_step bien escalado para alcanzar target_pos_fn(t1)."""
    target_r = np.asarray(target_pos_fn(t1), dtype=np.float64)
    scale = 100.0

    def res_fn(dv: np.ndarray) -> np.ndarray:
        v_try = v0_guess + dv * scale
        sol = _propagate_3d(
            bodies,
            np.concatenate((r0, v_try)),
            t0,
            t1,
            rtol=1e-7,
            atol=1e-7,
            dense_output=False,
            strict_impact=False,
        )
        if not sol.success:
            return np.full(3, 1e6)
        return (sol.y[:3, -1] - target_r) / 1000.0

    opt = least_squares(
        res_fn,
        np.zeros(3, dtype=np.float64),
        method="trf",
        bounds=(-25.0, 25.0),
        diff_step=1e-3,
        ftol=1e-5,
        xtol=1e-5,
        gtol=1e-5,
        max_nfev=24,
    )
    v0_opt = v0_guess + opt.x * scale
    sol_final = _propagate_3d(
        bodies,
        np.concatenate((r0, v0_opt)),
        t0,
        t1,
        rtol=1e-9,
        atol=1e-9,
        dense_output=True,
        strict_impact=True,
        max_step=3600.0,
    )
    if not sol_final.success or sol_final.y.size == 0:
        return False, v0_opt, sol_final
    err_m = float(np.linalg.norm(sol_final.y[:3, -1] - target_r))
    return bool(err_m <= tol_m), v0_opt, sol_final


def _min_body_altitude(sol, body, t0: float, t1: float, n: int = 240, *, refine: bool = True) -> tuple[float, float]:
    """Devuelve (altitud_minima_m, instante_t_s) de una solución densa respecto a un cuerpo."""
    if not (t0 < t1):
        raise ValueError("El intervalo de búsqueda de altitud debe tener duración positiva.")
    ts = np.linspace(t0, t1, n)
    ys = np.asarray(sol.sol(ts)[:3]).T
    motion = getattr(body, "_motion", None)
    b_pos = np.asarray(motion(ts)) if callable(motion) else np.asarray([body.pos(float(t)) for t in ts])
    dists = np.linalg.norm(ys - b_pos, axis=1)
    idx = int(np.argmin(dists))
    lo, hi = ts[max(0, idx - 1)], ts[min(n - 1, idx + 1)]
    if refine and lo < hi:
        local = minimize_scalar(
            lambda t: float(np.linalg.norm(np.asarray(sol.sol(t)[:3]) - np.asarray(body.pos(t)))),
            bounds=(float(lo), float(hi)),
            method="bounded",
            options={"xatol": 0.1, "maxiter": 30},
        )
        if local.success and local.fun < dists[idx]:
            return float(local.fun - body.radius_m), float(local.x)
    return float(dists[idx] - body.radius_m), float(ts[idx])


def optimize_round_trip_transfer(
    date: datetime,
    *,
    mode: Literal["free_return", "lunar_orbit"] = "free_return",
    max_total_duration_s: float = 14 * 86400.0,
    parking_alt_m: float = DEFAULT_PARKING_ALT_M,
    lunar_periapsis_alt_m: float = 150_000.0,
    lunar_stay_s: float = 0.0,
    reentry_alt_m: float = 120_000.0,
    mass_kg: float = 1.0,
) -> RoundTripResult:
    """Optimiza una misión 3D completa Tierra → Luna → Tierra sin tocar la Luna."""
    if mode not in ("free_return", "lunar_orbit"):
        raise ValueError("mode debe ser 'free_return' o 'lunar_orbit'.")
    if not all(
        np.isfinite(x)
        for x in (
            max_total_duration_s,
            parking_alt_m,
            lunar_periapsis_alt_m,
            lunar_stay_s,
            reentry_alt_m,
            mass_kg,
        )
    ):
        raise ValueError("Los parámetros numéricos de misión deben ser finitos.")
    if (
        parking_alt_m < 100_000.0
        or lunar_periapsis_alt_m < 20_000.0
        or lunar_stay_s < 0.0
        or reentry_alt_m < 50_000.0
        or mass_kg <= 0
    ):
        raise ValueError("Altitudes, estancia o masa fuera del dominio físico permitido.")
    if mode == "free_return" and lunar_stay_s > 0:
        raise ValueError("free_return no admite estancia orbital.")
    if max_total_duration_s < 5.5 * 86400.0 + lunar_stay_s:
        raise NoFeasibleTransfer(
            [
                "max_total_duration_s es demasiado corto para completar ida, estancia y retorno "
                f"(mínimo recomendado: {(5.5 * 86400.0 + lunar_stay_s) / 86400.0:.1f} días)."
            ]
        )

    scenario = SpatialScenario(date, max_total_duration_s, spacing_s=600.0, include_sun=True)
    earth = scenario.bodies["earth"]
    moon = scenario.bodies["moon"]
    bodies = tuple(scenario.get_bodies())

    e_pos_0 = np.asarray(earth.pos(0.0), dtype=np.float64)
    e_vel_0 = np.asarray(earth.speed(0.0), dtype=np.float64)
    r_p_moon = moon.radius_m + lunar_periapsis_alt_m
    r_reentry = earth.radius_m + reentry_alt_m
    v_circ_moon = float(np.sqrt(moon.mu_m3_s2 / r_p_moon))
    _, _, u_h_0 = _orbital_basis(earth, moon, 0.0)

    reasons: list[str] = []
    best_rt: RoundTripResult | None = None
    out_durations = [
        d * 86400.0
        for d in (3.0, 3.5, 4.0, 4.5, 5.0)
        if d * 86400.0 + lunar_stay_s + 2.2 * 86400.0 <= max_total_duration_s
    ]

    if mode == "free_return":
        target_return_perigee_m = 0.65 * reentry_alt_m

        for t_out in out_durations:
            m_pos_1 = np.asarray(moon.pos(t_out), dtype=np.float64)
            e_pos_1 = np.asarray(earth.pos(t_out), dtype=np.float64)
            u_far_side = (m_pos_1 - e_pos_1) / np.linalg.norm(m_pos_1 - e_pos_1)

            # Aproximación por la cara exterior de la Luna.
            target_peri = m_pos_1 + r_p_moon * u_far_side
            seed_aim = m_pos_1 + 5_500_000.0 * u_far_side

            ranked_seeds: list[
                tuple[float, np.ndarray, np.ndarray, np.ndarray]
            ] = []

            for alpha in _aligned_launch_angles(
                earth, moon, t_out, (6.0, 13.0, 20.0, 27.0, 34.0)
            ):
                r0, v_park = _parking_state_3d(
                    earth, moon, alpha, parking_alt_m
                )
                rel_r1 = r0 - e_pos_0
                rel_r2 = seed_aim - e_pos_1
                p_norm = _lambert_plane_normal(rel_r1, rel_r2, u_h_0)

                try:
                    seed = solve_lambert(
                        tuple(rel_r1),
                        tuple(rel_r2),
                        t_out,
                        earth.mu_m3_s2,
                        prograde=True,
                        plane_normal=p_norm,
                    )
                except (LambertError, ValueError, ArithmeticError):
                    continue

                v_guess = e_vel_0 + np.asarray(
                    seed.departure_velocity_m_s, dtype=np.float64
                )
                ranked_seeds.append(
                    (
                        float(np.linalg.norm(v_guess - v_park)),
                        r0,
                        v_park,
                        v_guess,
                    )
                )

            ranked_seeds.sort(key=lambda item: item[0])

            for _, r0, v_park, v_guess in ranked_seeds[:2]:
                ok_out, v0_base, _ = _shoot_3d_target(
                    bodies,
                    r0,
                    v_guess,
                    0.0,
                    t_out,
                    lambda _t, p=target_peri: p,
                    tol_m=30_000.0,
                )
                if not ok_out:
                    reasons.append("No convergió la aproximación al perilunio")
                    continue

                u_t0 = (v_park - e_vel_0) / np.linalg.norm(v_park - e_vel_0)
                u_r0 = (r0 - e_pos_0) / np.linalg.norm(r0 - e_pos_0)

                def _fr_two_param(params: np.ndarray) -> np.ndarray:
                    v_try = (
                        v0_base
                        + (params[0] * 10.0) * u_t0
                        + (params[1] * 10.0) * u_r0
                    )
                    sol = _propagate_3d(
                        bodies,
                        np.concatenate((r0, v_try)),
                        0.0,
                        max_total_duration_s,
                        rtol=1e-10,
                        atol=1e-9,
                        dense_output=True,
                        strict_impact=False,
                    )
                    if not sol.success:
                        return np.array([1e5, 1e5])

                    min_m_alt, t_pm = _min_body_altitude(
                        sol,
                        moon,
                        0.5 * t_out,
                        min(max_total_duration_s, 1.5 * t_out),
                        n=160,
                        refine=True,
                    )

                    # Penalización si la trayectoria baja de 25 km.
                    penetration = max(0.0, 25_000.0 - min_m_alt) / 10_000.0
                    t_ret_start = min(
                        max_total_duration_s - 3600.0,
                        t_pm + 0.75 * 86400.0,
                    )
                    min_e_alt, _ = _min_body_altitude(
                        sol,
                        earth,
                        t_ret_start,
                        max_total_duration_s,
                        n=240,
                        refine=True,
                    )

                    return np.array(
                        [
                            (min_m_alt - lunar_periapsis_alt_m) / 50_000.0
                            - penetration,
                            (min_e_alt - target_return_perigee_m) / 200_000.0,
                        ]
                    )

                def _fr_jac(params: np.ndarray) -> np.ndarray:
                    # Paso absoluto para evitar diferencias demasiado pequeñas.
                    step = 1e-3
                    return np.column_stack(
                        [
                            (
                                _fr_two_param(params + step * np.eye(2)[i])
                                - _fr_two_param(params - step * np.eye(2)[i])
                            )
                            / (2 * step)
                            for i in range(2)
                        ]
                    )

                fit = least_squares(
                    _fr_two_param,
                    np.zeros(2, dtype=np.float64),
                    method="trf",
                    bounds=([-25.0, -100.0], [25.0, 100.0]),
                    jac=_fr_jac,
                    ftol=1e-5,
                    xtol=1e-5,
                    gtol=1e-5,
                    max_nfev=60,
                )
                v0_opt = (
                    v0_base
                    + (fit.x[0] * 10.0) * u_t0
                    + (fit.x[1] * 10.0) * u_r0
                )

                sol_full = _propagate_3d(
                    bodies,
                    np.concatenate((r0, v0_opt)),
                    0.0,
                    max_total_duration_s,
                    rtol=1e-9,
                    atol=1e-9,
                    dense_output=True,
                    strict_impact=True,
                    reentry_radius_m=r_reentry,
                    reentry_after_s=t_out + 0.75 * 86400.0,
                    max_step=3600.0,
                )
                hit_reentry = (
                    sol_full.t_events is not None
                    and len(sol_full.t_events) >= 3
                    and len(sol_full.t_events[2]) > 0
                )
                t_eval_end = float(sol_full.t[-1])

                if (
                    not sol_full.success
                    or not hit_reentry
                    or t_eval_end <= t_out + 1.5 * 86400.0
                ):
                    reasons.append(
                        "La trayectoria de retorno libre no completó "
                        "la reentrada segura"
                    )
                    continue

                t_reentry = float(sol_full.t_events[2][0])
                min_m_alt, t_peri_m = _min_body_altitude(
                    sol_full,
                    moon,
                    0.5 * t_out,
                    min(t_reentry, 1.5 * t_out),
                )

                if (
                    min_m_alt < 20_000.0
                    or abs(min_m_alt - lunar_periapsis_alt_m) > 80_000.0
                ):
                    reasons.append(
                        f"Perilunio fuera de seguridad ({min_m_alt / 1000:.1f} km)"
                    )
                    continue

                tli_dv = float(np.linalg.norm(v0_opt - v_park))
                actual_reentry_alt = float(
                    np.linalg.norm(
                        sol_full.sol(t_reentry)[:3]
                        - np.asarray(earth.pos(t_reentry))
                    )
                    - earth.radius_m
                )

                cand_rt = RoundTripResult(
                    scenario=scenario,
                    mode="free_return",
                    outbound_duration_s=float(t_peri_m),
                    lunar_stay_s=0.0,
                    inbound_duration_s=float(t_reentry - t_peri_m),
                    total_duration_s=float(t_reentry),
                    tli_delta_v_m_s=tli_dv,
                    loi_delta_v_m_s=0.0,
                    tei_delta_v_m_s=0.0,
                    total_delta_v_m_s=tli_dv,
                    min_lunar_altitude_m=float(min_m_alt),
                    earth_reentry_altitude_m=float(actual_reentry_alt),
                    mass_kg=float(mass_kg),
                    _segments=((0.0, float(t_reentry), sol_full),),
                )

                if (
                    best_rt is None
                    or cand_rt.total_delta_v_m_s < best_rt.total_delta_v_m_s
                ):
                    best_rt = cand_rt

            if best_rt is not None:
                break

    else:
        # Modo lunar_orbit: TLI -> LOI en perilunio -> Estancia -> TEI hiperbólica -> Reentrada
        lunar_orbit_period_s = float(2.0 * np.pi * np.sqrt(r_p_moon**3 / moon.mu_m3_s2))

        for t_out in out_durations:
            remaining_base = max_total_duration_s - (t_out + lunar_stay_s)
            if remaining_base < 2.2 * 86400.0:
                continue

            m_pos_1 = np.asarray(moon.pos(t_out), dtype=np.float64)
            m_vel_1 = np.asarray(moon.speed(t_out), dtype=np.float64)
            e_pos_1 = np.asarray(earth.pos(t_out), dtype=np.float64)

            u_em_1 = m_pos_1 - e_pos_1
            u_em_1 /= np.linalg.norm(u_em_1)
            target_peri_1 = m_pos_1 + r_p_moon * u_em_1
            seed_aim_1 = m_pos_1 + (r_p_moon + 2_200_000.0) * u_em_1

            ranked_out: list[tuple[float, np.ndarray, np.ndarray, np.ndarray]] = []
            for alpha in _aligned_launch_angles(earth, moon, t_out, (6.0, 14.0, 22.0, 30.0)):
                r0, v_park = _parking_state_3d(earth, moon, alpha, parking_alt_m)
                rel_r1 = r0 - e_pos_0
                rel_r2 = seed_aim_1 - e_pos_1
                p_norm = _lambert_plane_normal(rel_r1, rel_r2, u_h_0)
                try:
                    seed_out = solve_lambert(
                        tuple(rel_r1),
                        tuple(rel_r2),
                        t_out,
                        earth.mu_m3_s2,
                        prograde=True,
                        plane_normal=p_norm,
                    )
                except (LambertError, ValueError, ArithmeticError):
                    continue
                v_guess_out = e_vel_0 + np.asarray(seed_out.departure_velocity_m_s, dtype=np.float64)
                ranked_out.append((float(np.linalg.norm(v_guess_out - v_park)), r0, v_park, v_guess_out))

            ranked_out.sort(key=lambda item: item[0])

            for _, r0, v_park, v_guess_out in ranked_out[:2]:
                ok_out, v0_opt, sol_out = _shoot_3d_target(
                    bodies, r0, v_guess_out, 0.0, t_out, lambda _t, p=target_peri_1: p, tol_m=15_000.0
                )
                if not ok_out:
                    reasons.append("Tramo de ida no convergió al perilunio")
                    continue

                tli_dv = float(np.linalg.norm(v0_opt - v_park))
                r_arr_m = sol_out.y[:3, -1]
                v_arr_m = sol_out.y[3:, -1]

                # Inserción circular en órbita lunar (LOI)
                r_rel_m = r_arr_m - m_pos_1
                v_rel_m = v_arr_m - m_vel_1
                u_r_m = r_rel_m / np.linalg.norm(r_rel_m)
                h_m = np.cross(r_rel_m, v_rel_m)
                norm_hm = float(np.linalg.norm(h_m))
                if norm_hm == 0.0:
                    continue
                u_hm = h_m / norm_hm
                u_t_m = np.cross(u_hm, u_r_m)
                v_loi_inertial = m_vel_1 + v_circ_moon * u_t_m
                loi_dv = float(np.linalg.norm(v_loi_inertial - v_arr_m))

                base_depart = t_out + lunar_stay_s
                t_in = min(t_out, max_total_duration_s - (base_depart + lunar_orbit_period_s))
                if t_in < 2.2 * 86400.0:
                    t_in = min(t_out, max_total_duration_s - base_depart)
                if t_in < 2.2 * 86400.0:
                    continue

                t_end_est = base_depart + t_in
                e_pos_end = np.asarray(earth.pos(t_end_est), dtype=np.float64)
                m_pos_dep = np.asarray(moon.pos(base_depart), dtype=np.float64)
                m_vel_dep = np.asarray(moon.speed(base_depart), dtype=np.float64)
                u_to_earth = (e_pos_end - m_pos_dep) / np.linalg.norm(e_pos_end - m_pos_dep)
                u_perp_e = np.cross(u_h_0, u_to_earth)
                u_perp_e /= np.linalg.norm(u_perp_e)
                target_reentry = e_pos_end + r_reentry * u_perp_e

                rel_in_1 = m_pos_dep - np.asarray(earth.pos(base_depart))
                rel_in_2 = target_reentry - e_pos_end
                p_norm_in = _lambert_plane_normal(rel_in_1, rel_in_2, u_h_0)
                try:
                    seed_in = solve_lambert(
                        tuple(rel_in_1),
                        tuple(rel_in_2),
                        t_in,
                        earth.mu_m3_s2,
                        prograde=True,
                        plane_normal=p_norm_in,
                    )
                except (LambertError, ValueError, ArithmeticError):
                    continue

                v_inf_dep = (
                    np.asarray(earth.speed(base_depart), dtype=np.float64)
                    + np.asarray(seed_in.departure_velocity_m_s, dtype=np.float64)
                    - m_vel_dep
                )
                v_inf_mag = float(np.linalg.norm(v_inf_dep))
                v_peri_esc = float(np.sqrt(v_inf_mag**2 + 2.0 * moon.mu_m3_s2 / r_p_moon))
                ecc_hyp = 1.0 + (r_p_moon * v_inf_mag**2) / moon.mu_m3_s2
                beta_turn = float(np.arcsin(min(1.0, 1.0 / ecc_hyp)))

                v_inf_plane = v_inf_dep - float(np.dot(v_inf_dep, u_hm)) * u_hm
                norm_vip = float(np.linalg.norm(v_inf_plane))
                u_v_inf = v_inf_plane / norm_vip if norm_vip > 0 else -m_vel_dep / np.linalg.norm(m_vel_dep)
                u_v_req = math.cos(beta_turn) * u_v_inf - math.sin(beta_turn) * np.cross(u_hm, u_v_inf)

                max_stay_end = min(
                    base_depart + lunar_orbit_period_s,
                    max_total_duration_s - 2.2 * 86400.0,
                )
                sol_stay_base = None
                t_depart_moon = base_depart
                r_tei = r_arr_m
                v_pre_tei = v_loi_inertial

                if max_stay_end > t_out + 60.0:
                    sol_stay_base = _propagate_3d(
                        bodies,
                        np.concatenate((r_arr_m, v_loi_inertial)),
                        t_out,
                        max_stay_end,
                        rtol=1e-8,
                        atol=1e-8,
                        dense_output=True,
                        strict_impact=True,
                        max_step=1800.0,
                    )
                    if not sol_stay_base.success:
                        reasons.append("La órbita lunar intermedia impactó la Luna")
                        continue

                    sample_times = np.linspace(min(base_depart, max_stay_end), max_stay_end, 36)
                    best_align = -2.0
                    for t_cand in sample_times:
                        y_c = sol_stay_base.sol(float(t_cand))
                        v_rel_c = y_c[3:] - np.asarray(moon.speed(float(t_cand)))
                        u_v_c = v_rel_c / np.linalg.norm(v_rel_c)
                        align = float(np.dot(u_v_c, u_v_req))
                        if align > best_align:
                            best_align = align
                            t_depart_moon = float(t_cand)

                    y_tei = sol_stay_base.sol(t_depart_moon)
                    r_tei = y_tei[:3]
                    v_pre_tei = y_tei[3:]

                t_end = t_depart_moon + t_in
                if t_end > max_total_duration_s:
                    t_end = max_total_duration_s
                    t_in = t_end - t_depart_moon
                if t_in < 2.2 * 86400.0:
                    continue

                e_pos_end = np.asarray(earth.pos(t_end), dtype=np.float64)
                u_to_earth = (e_pos_end - r_tei) / np.linalg.norm(e_pos_end - r_tei)
                u_perp_e = np.cross(u_h_0, u_to_earth)
                u_perp_e /= np.linalg.norm(u_perp_e)
                target_reentry = e_pos_end + r_reentry * u_perp_e

                v_rel_pre = v_pre_tei - np.asarray(moon.speed(t_depart_moon))
                u_v_tan = v_rel_pre / np.linalg.norm(v_rel_pre)
                v_guess_in = (
                    np.asarray(moon.speed(t_depart_moon), dtype=np.float64)
                    + v_peri_esc * u_v_tan
                    + float(np.dot(v_inf_dep, u_hm)) * u_hm
                )

                ok_in, v_tei_opt, sol_in = _shoot_3d_target(
                    bodies,
                    r_tei,
                    v_guess_in,
                    t_depart_moon,
                    t_end,
                    lambda _t, p=target_reentry: p,
                    tol_m=30_000.0,
                )
                if not ok_in:
                    reasons.append("Tramo de retorno no convergió a la reentrada terrestre")
                    continue

                tei_dv = float(np.linalg.norm(v_tei_opt - v_pre_tei))
                total_dv = float(tli_dv + loi_dv + tei_dv)
                min_m_alt, _ = _min_body_altitude(sol_out, moon, 0.5 * t_out, t_out)
                min_e_alt, _ = _min_body_altitude(sol_in, earth, t_depart_moon + 0.5 * t_in, t_end)
                actual_reentry_alt = float(
                    np.linalg.norm(sol_in.y[:3, -1] - np.asarray(earth.pos(t_end))) - earth.radius_m
                )

                if (
                    min_m_alt < 20_000.0
                    or abs(min_m_alt - lunar_periapsis_alt_m) > 40_000.0
                    or min_e_alt < 0.0
                    or abs(actual_reentry_alt - reentry_alt_m) > 40_000.0
                ):
                    reasons.append("Perilunio o reentrada terrestre fuera del corredor")
                    continue

                min_stay_alt = min_m_alt
                segments = [(0.0, float(t_out), sol_out)]
                if sol_stay_base is not None and t_depart_moon > t_out:
                    min_stay_alt, _ = _min_body_altitude(sol_stay_base, moon, t_out, t_depart_moon)
                    if min_stay_alt < 20_000.0:
                        reasons.append("La órbita lunar intermedia cruza la superficie")
                        continue
                    segments.append((float(t_out), float(t_depart_moon), sol_stay_base))
                segments.append((float(t_depart_moon), float(t_end), sol_in))

                cand_rt = RoundTripResult(
                    scenario=scenario,
                    mode="lunar_orbit",
                    outbound_duration_s=float(t_out),
                    lunar_stay_s=float(t_depart_moon - t_out),
                    inbound_duration_s=float(t_end - t_depart_moon),
                    total_duration_s=float(t_end),
                    tli_delta_v_m_s=tli_dv,
                    loi_delta_v_m_s=loi_dv,
                    tei_delta_v_m_s=tei_dv,
                    total_delta_v_m_s=total_dv,
                    min_lunar_altitude_m=float(min(min_m_alt, min_stay_alt)),
                    earth_reentry_altitude_m=float(actual_reentry_alt),
                    mass_kg=float(mass_kg),
                    _segments=tuple(segments),
                )
                if best_rt is None or cand_rt.total_delta_v_m_s < best_rt.total_delta_v_m_s:
                    best_rt = cand_rt
            if best_rt is not None:
                break

    if best_rt is None:
        raise NoFeasibleTransfer(
            reasons or ["No se encontró ninguna trayectoria de retorno viable en la ventana dada."]
        )
    return best_rt