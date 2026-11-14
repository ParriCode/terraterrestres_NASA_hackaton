from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

import numpy as np

from app.data.scenarios import PlanarScenario
from app.physics.lambert import LambertError, solve_lambert
from app.services.transfer_service import (
    F,
    TransferNotFoundError,
    TransferResult,
    orbit_point,
    prograde_circular_velocity,
)

DEFAULT_PARKING_ALT_M = 200_000.0
DEFAULT_MIN_DURATION_S = 2.5 * 86400.0
DEFAULT_DURATION_STEP_S = 0.5 * 86400.0
DEFAULT_LAUNCH_ANGLES_DEG: tuple[float, ...] = tuple(float(a) for a in range(0, 360, 12))
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
        super().__init__("; ".join(self.reasons) if self.reasons else "No se encontró transferencia factible.")


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
    h_z = float(r1[0] * v1[1] - r1[1] * v1[0])
    ecc_vec = ((v_sq - mu_earth / r_mag) * r1 - float(np.dot(r1, v1)) * v1) / mu_earth
    ecc = float(np.linalg.norm(ecc_vec))
    return float((h_z * h_z) / (mu_earth * (1.0 + ecc)))


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

    upper_s = float(scenario.duration_s if max_duration_s is None else min(max_duration_s, scenario.duration_s))
    durations = _duration_grid(min_duration_s, upper_s, duration_step_s)
    if not durations:
        return []

    earth = scenario.bodies["earth"]
    moon = scenario.bodies["moon"]
    earth_pos_0 = np.asarray(earth.pos(0.0))
    v_esc_moon = float(np.sqrt(2.0 * moon.mu_m3_s2 / moon.radius_m))

    launch_points: list[tuple[float, np.ndarray, np.ndarray, np.ndarray]] = []
    for alpha in launch_angles_deg:
        p0 = np.asarray(orbit_point(earth, moon, 0.0, alpha, parking_alt_m))
        r1 = p0 - earth_pos_0
        v_circ = prograde_circular_velocity(earth.mu_m3_s2, r1)
        launch_points.append((float(alpha), p0, r1, v_circ))

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

        for alpha, _, r1, v_circ in launch_points:
            r1_tuple = (float(r1[0]), float(r1[1]), 0.0)
            for beta, p1 in arrival_points:
                r2 = p1 - earth_pos_t1
                r2_tuple = (float(r2[0]), float(r2[1]), 0.0)
                r_moon_surf = p1 - moon_pos_t1
                for prograde in prograde_options:
                    try:
                        seed = solve_lambert(r1_tuple, r2_tuple, duration_s, earth.mu_m3_s2, prograde=prograde)
                    except (LambertError, ValueError, ArithmeticError):
                        continue
                    v_dep_rel = np.asarray(seed.departure_velocity_m_s)
                    # Descartar salidas hacia abajo cuyo periapsis dos-cuerpos atraviesa la Tierra.
                    if float(np.dot(r1, v_dep_rel)) < -1.0:
                        if _lambert_periapsis_m(r1, v_dep_rel, earth.mu_m3_s2) < earth.radius_m:
                            continue
                    v_arr_bary = earth_vel_t1 + np.asarray(seed.arrival_velocity_m_s)
                    v_inf_vec = v_arr_bary - moon_vel_t1
                    # Descartar puntos de llegada en el hemisferio lunar saliente.
                    if float(np.dot(v_inf_vec, r_moon_surf)) >= 0.0:
                        continue

                    launch_dv = float(np.linalg.norm(v_dep_rel - v_circ))
                    v_inf = float(np.linalg.norm(v_inf_vec))
                    arrival_dv = float(np.hypot(v_inf, v_esc_moon))
                    total_dv = float(launch_dv + arrival_dv)
                    candidates.append(Candidate(
                        duration_s=float(duration_s),
                        launch_angle_deg=alpha,
                        arrival_angle_deg=beta,
                        prograde=bool(prograde),
                        estimated_launch_delta_v_m_s=launch_dv,
                        estimated_v_infinity_m_s=v_inf,
                        estimated_arrival_delta_v_m_s=arrival_dv,
                        estimated_total_delta_v_m_s=total_dv,
                    ))

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
    """Refinamiento local por coordenadas sobre (duración, α, β) manteniendo el límite."""
    best_result = initial_result
    best_duration = initial_candidate.duration_s
    best_alpha = initial_candidate.launch_angle_deg
    best_beta = initial_candidate.arrival_angle_deg
    evaluations = 0

    schedules = (
        (0.25 * 86400.0, 6.0, 20.0),
        (0.10 * 86400.0, 3.0, 10.0),
    )
    for dt_step, dalpha_step, dbeta_step in schedules:
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
                    scenario, dur, alpha, beta,
                    parking_alt_m=parking_alt_m, mass_kg=mass_kg,
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
        estimated_launch_delta_v_m_s=initial_candidate.estimated_launch_delta_v_m_s,
        estimated_v_infinity_m_s=initial_candidate.estimated_v_infinity_m_s,
        estimated_arrival_delta_v_m_s=initial_candidate.estimated_arrival_delta_v_m_s,
        estimated_total_delta_v_m_s=initial_candidate.estimated_total_delta_v_m_s,
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
    top_k: int = 6,
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

    diverse = deduplicate_candidates(candidates, limit=top_k)
    shortlist = list(diverse)
    if len(shortlist) < top_k:
        for cand in candidates:
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
                )
                validated.append((res, cand))
            except (TransferNotFoundError, LambertError, ValueError, RuntimeError) as error:
                reasons.append(str(error))

    try_candidates(shortlist)
    if not validated:
        fallback = [c for c in candidates[: max(top_k * 2, 12)] if c not in shortlist]
        try_candidates(fallback)

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
