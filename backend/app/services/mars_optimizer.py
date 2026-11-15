"""Transferencia Tierra → Marte de solo ida (módulo aislado; no toca la lógica lunar).

Física: cónicas parcheadas para el cribado + propagación N-cuerpos 3D (DOP853) para validar.

1. Cribado heliocéntrico con Lambert (arco prógrado) para tiempos de vuelo de 120 días hasta
   ``max_duration_s`` en pasos de 5 días. Δv impulsivos por conservación de energía:
   TMI desde LEO circular y MOI en el periapsis marciano.
2. Para los mejores candidatos se construye el estado inicial en LEO alineado con la asíntota
   de salida, se propaga con gravedad de Sol, Tierra, Luna y Marte y se corrige v0 por disparo
   (Newton con jacobiano por diferencias + actualizaciones de Broyden) hasta llegar al
   periapsis objetivo de Marte en t1.
3. Se devuelven trayectoria muestreable, Δv TMI/MOI medidos sobre la trayectoria propagada,
   altitud mínima en Marte, curva de compromiso Δv–días y masa de propelente (Tsiolkovski).

Marco: el de ``SpatialScenario`` (centro baricentro Tierra–Luna 500@3, base del plano orbital
Tierra–Luna). Las magnitudes heliocéntricas se obtienen restando la posición/velocidad del Sol.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import math
from typing import Sequence

import numpy as np

from app.mission.data.scenarios import SpatialScenario
from app.mission.models.domain import SpacecraftState, Vec3
from app.mission.physics.lambert import LambertError, solve_lambert
from app.mission.services.propulsion import PropellantEstimate, estimate_propellant
from app.services.mission_optimizer import _min_body_altitude, _propagate_3d

DAY_S = 86400.0
MIN_DURATION_S = 120 * DAY_S
DURATION_STEP_S = 5 * DAY_S
DEFAULT_PARKING_ALT_M = 200_000.0
DEFAULT_MARS_PERIAPSIS_ALT_M = 300_000.0
DEFAULT_ISP_S = 320.0  # bipropelente almacenable típico (orden de magnitud de etapas de inyección)
SCENARIO_SPACING_S = 3600.0
# Tolerancia del disparo: distancia al punto de periapsis objetivo en t1.
ARRIVAL_TOLERANCE_M = 50_000.0


@dataclass(frozen=True)
class MarsCandidate:
    duration_s: float
    v_inf_departure_m_s: float
    v_inf_arrival_m_s: float
    tmi_delta_v_m_s: float
    moi_delta_v_m_s: float
    total_delta_v_m_s: float
    v_inf_departure_vec: tuple[float, float, float]
    v_inf_arrival_vec: tuple[float, float, float]


@dataclass(frozen=True)
class MarsTradeoffPoint:
    """Mismo contrato que la curva lunar (launch = TMI, arrival = MOI)."""

    duration_s: float
    estimated_launch_delta_v_m_s: float
    estimated_arrival_delta_v_m_s: float
    estimated_total_delta_v_m_s: float


@dataclass(frozen=True)
class MarsTransferResult:
    scenario: SpatialScenario
    duration_s: float
    tmi_delta_v_m_s: float
    moi_delta_v_m_s: float
    total_delta_v_m_s: float
    estimated_total_delta_v_m_s: float
    v_inf_departure_m_s: float
    v_inf_arrival_m_s: float
    min_mars_altitude_m: float
    min_mars_altitude_t_s: float
    arrival_error_m: float
    parking_alt_m: float
    mars_periapsis_alt_m: float
    mass_kg: float
    propellant: PropellantEstimate
    tradeoff: list[MarsTradeoffPoint]
    candidates_evaluated: int
    propagations_run: int
    # Compatibilidad con el serializador de muestras del controlador (segmentos densos 3D).
    _segments: tuple[tuple[float, float, object], ...] = field(repr=False, default=())

    @property
    def total_duration_s(self) -> float:
        return self.duration_s

    def state(self, time_s: float) -> SpacecraftState:
        if not np.isfinite(time_s) or not 0.0 <= time_s <= self.duration_s + 1e-6:
            raise ValueError("Tiempo fuera del intervalo de la transferencia a Marte.")
        _, _, sol = self._segments[0]
        y = sol.sol(float(np.clip(time_s, 0.0, self.duration_s)))
        return SpacecraftState((float(y[0]), float(y[1]), float(y[2])), (float(y[3]), float(y[4]), float(y[5])))

    def pos(self, time_s: float) -> Vec3:
        return self.state(time_s).position_m

    def speed(self, time_s: float) -> Vec3:
        return self.state(time_s).velocity_m_s


class NoFeasibleMarsTransfer(RuntimeError):
    def __init__(self, reasons: Sequence[str], tradeoff: Sequence[MarsTradeoffPoint] = (), *, max_duration_s: float = 0.0):
        self.reasons = list(dict.fromkeys(reasons))
        self.tradeoff = list(tradeoff)
        self.max_duration_s = float(max_duration_s)
        super().__init__("; ".join(self.reasons) if self.reasons else "No se encontró transferencia a Marte factible.")


# --------------------------------------------------------------------------- utilidades


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n == 0.0:
        raise ValueError("Vector nulo.")
    return v / n


def _vec(body, t_s: float) -> tuple[np.ndarray, np.ndarray]:
    return np.asarray(body.pos(t_s), dtype=np.float64), np.asarray(body.velocity(t_s), dtype=np.float64)


def hyperbolic_delta_v(v_inf_m_s: float, mu_m3_s2: float, r_m: float) -> float:
    """Δv impulsivo entre órbita circular de radio r y la hipérbola de exceso v∞ (energía)."""
    return math.sqrt(v_inf_m_s ** 2 + 2.0 * mu_m3_s2 / r_m) - math.sqrt(mu_m3_s2 / r_m)


def departure_perigee_state(
    v_inf_vec: np.ndarray, mu_m3_s2: float, r_park_m: float, plane_ref: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Dirección radial y de velocidad en el perigeo de una hipérbola de salida.

    El plano orbital contiene v∞ y es lo más prógrado posible respecto a ``plane_ref``
    (n = norm(z − (z·v̂)v̂), p = n × v̂). Con e = 1 + r v∞²/μ y β = arccos(1/e), el ángulo
    entre el perigeo y la asíntota de salida es ν∞ = π − β, de modo que:
        r̂0 = −cos β · v̂∞ − sin β · p̂        v̂0 = sin β · v̂∞ − cos β · p̂
    (r̂0 ⟂ v̂0 y la hipérbola, recorrida desde el perigeo, sale en la dirección +v̂∞).
    Devuelve (r̂0, v̂0, v_perigeo).
    """
    v_inf = float(np.linalg.norm(v_inf_vec))
    s_hat = _unit(v_inf_vec)
    n_hat = _unit(plane_ref - float(np.dot(plane_ref, s_hat)) * s_hat)
    p_hat = np.cross(n_hat, s_hat)
    e = 1.0 + r_park_m * v_inf ** 2 / mu_m3_s2
    beta = math.acos(1.0 / e)
    r_hat = -math.cos(beta) * s_hat - math.sin(beta) * p_hat
    v_hat = math.sin(beta) * s_hat - math.cos(beta) * p_hat
    v_p = math.sqrt(v_inf ** 2 + 2.0 * mu_m3_s2 / r_park_m)
    return r_hat, v_hat, v_p


def arrival_periapsis_direction(v_inf_vec: np.ndarray, mu_m3_s2: float, r_p_m: float, plane_ref: np.ndarray) -> np.ndarray:
    """Dirección del periapsis de la hipérbola de llegada (plano prógrado respecto a plane_ref).

    La nave llega desde −v̂∞; el periapsis forma ν∞ = π − β con esa dirección:
        r̂p = cos β · v̂∞ − sin β · p̂   (mismo sentido de giro que la salida).
    """
    v_inf = float(np.linalg.norm(v_inf_vec))
    s_hat = _unit(v_inf_vec)
    n_hat = _unit(plane_ref - float(np.dot(plane_ref, s_hat)) * s_hat)
    p_hat = np.cross(n_hat, s_hat)
    beta = math.acos(1.0 / (1.0 + r_p_m * v_inf ** 2 / mu_m3_s2))
    return math.cos(beta) * s_hat - math.sin(beta) * p_hat


# --------------------------------------------------------------------------- 1. cribado


def screen_lambert(
    scenario: SpatialScenario,
    max_duration_s: float,
    *,
    parking_alt_m: float = DEFAULT_PARKING_ALT_M,
    mars_periapsis_alt_m: float = DEFAULT_MARS_PERIAPSIS_ALT_M,
    min_duration_s: float = MIN_DURATION_S,
    step_s: float = DURATION_STEP_S,
) -> list[MarsCandidate]:
    """Lambert heliocéntrico prógrado para cada tiempo de vuelo; ordenado por Δv total."""
    earth, mars, sun = (scenario.bodies[k] for k in ("earth", "mars", "sun"))
    r_leo = earth.radius_m + parking_alt_m
    r_pm = mars.radius_m + mars_periapsis_alt_m
    re0, ve0 = _vec(earth, 0.0)
    rs0, vs0 = _vec(sun, 0.0)
    r1 = re0 - rs0
    ve_helio = ve0 - vs0
    # Plano prógrado: momento angular heliocéntrico de la Tierra.
    h_earth = tuple(float(x) for x in _unit(np.cross(r1, ve_helio)))

    out: list[MarsCandidate] = []
    t = float(min_duration_s)
    while t <= max_duration_s + 1e-6:
        tof = min(t, float(max_duration_s))
        rm1, vm1 = _vec(mars, tof)
        rs1, vs1 = _vec(sun, tof)
        try:
            sol = solve_lambert(tuple(r1), tuple(rm1 - rs1), tof, sun.mu_m3_s2, prograde=True, plane_normal=h_earth)
        except (LambertError, ArithmeticError, ValueError):
            t += step_s
            continue
        v_dep = np.asarray(sol.departure_velocity_m_s) - ve_helio
        v_arr = np.asarray(sol.arrival_velocity_m_s) - (vm1 - vs1)
        vd, va = float(np.linalg.norm(v_dep)), float(np.linalg.norm(v_arr))
        tmi = hyperbolic_delta_v(vd, earth.mu_m3_s2, r_leo)
        moi = hyperbolic_delta_v(va, mars.mu_m3_s2, r_pm)
        out.append(MarsCandidate(tof, vd, va, tmi, moi, tmi + moi, tuple(map(float, v_dep)), tuple(map(float, v_arr))))
        t += step_s
    return sorted(out, key=lambda c: c.total_delta_v_m_s)


def build_tradeoff(candidates: Sequence[MarsCandidate]) -> list[MarsTradeoffPoint]:
    return [
        MarsTradeoffPoint(c.duration_s, c.tmi_delta_v_m_s, c.moi_delta_v_m_s, c.total_delta_v_m_s)
        for c in sorted(candidates, key=lambda c: c.duration_s)
    ]


# --------------------------------------------------------------------------- 2. disparo 3D


def _shoot(bodies, y0_pos, v0_guess, t1, target_fn, *, counter: list[int], tol_m: float, max_iter: int = 30):
    """Newton–Broyden sobre v0 para que r(t1) = objetivo. Devuelve (ok, v0, solución densa, error)."""
    target = np.asarray(target_fn(t1), dtype=np.float64)

    def miss(v0: np.ndarray) -> np.ndarray | None:
        counter[0] += 1
        sol = _propagate_3d(bodies, np.concatenate((y0_pos, v0)), 0.0, t1, rtol=1e-10, atol=1e-6,
                            dense_output=False, strict_impact=True)
        if not sol.success or sol.t[-1] < t1 - 1.0:
            return None
        return sol.y[:3, -1] - target

    v = np.array(v0_guess, dtype=np.float64)
    f = miss(v)
    if f is None:
        return False, v, None, math.inf

    def fd_jacobian(v: np.ndarray, f: np.ndarray, h: float) -> np.ndarray | None:
        J = np.empty((3, 3))
        for k in range(3):
            dv = np.zeros(3); dv[k] = h
            fk = miss(v + dv)
            if fk is None:
                return None
            J[:, k] = (fk - f) / h
        return J

    # Jacobiano inicial por diferencias (paso 1 cm/s: la sensibilidad desde LEO es enorme).
    J = fd_jacobian(v, f, 0.01)
    if J is None:
        return False, v, None, math.inf
    refreshes = 0
    for _ in range(max_iter):
        err = float(np.linalg.norm(f))
        if err <= tol_m:
            break
        try:
            step = -np.linalg.solve(J, f)
        except np.linalg.LinAlgError:
            step = None
        f_new = None
        if step is not None:
            # Amortiguación: limitar cada corrección a 50 m/s y reducir si empeora.
            n = float(np.linalg.norm(step))
            if n > 50.0:
                step *= 50.0 / n
            for _ in range(6):
                cand = miss(v + step)
                if cand is not None and float(np.linalg.norm(cand)) < err:
                    f_new = cand
                    break
                step *= 0.5
        if f_new is None:
            # Broyden se ha degradado: jacobiano completo de nuevo, con paso acorde al error.
            if refreshes >= 3:
                break
            refreshes += 1
            J = fd_jacobian(v, f, max(1e-4, min(0.01, err / 1e8)))
            if J is None:
                break
            continue
        # Actualización de Broyden (buena) del jacobiano.
        y = f_new - f
        J += np.outer(y - J @ step, step) / float(step @ step)
        v, f = v + step, f_new
    err = float(np.linalg.norm(f))
    final = _propagate_3d(bodies, np.concatenate((y0_pos, v)), 0.0, t1, rtol=1e-10, atol=1e-6,
                          dense_output=True, strict_impact=True)
    counter[0] += 1
    if not final.success:
        return False, v, None, err
    err = float(np.linalg.norm(final.y[:3, -1] - target))
    return err <= tol_m, v, final, err


def optimize_mars_transfer(
    date: datetime,
    max_duration_s: float,
    *,
    parking_alt_m: float = DEFAULT_PARKING_ALT_M,
    mars_periapsis_alt_m: float = DEFAULT_MARS_PERIAPSIS_ALT_M,
    mass_kg: float = 1000.0,
    isp_s: float = DEFAULT_ISP_S,
    candidates_to_refine: int = 3,
) -> MarsTransferResult:
    """Cribado Lambert + validación N-cuerpos 3D de la mejor transferencia Tierra → Marte."""
    if not np.isfinite(max_duration_s) or max_duration_s < MIN_DURATION_S:
        raise ValueError(f"max_duration_s debe ser al menos {MIN_DURATION_S / DAY_S:.0f} días.")
    if mass_kg <= 0 or isp_s <= 0:
        raise ValueError("mass_kg e isp_s deben ser positivos.")

    scenario = SpatialScenario(date, max_duration_s, spacing_s=SCENARIO_SPACING_S, include_mars=True)
    earth, moon, sun, mars = (scenario.bodies[k] for k in ("earth", "moon", "sun", "mars"))
    bodies = (earth, moon, sun, mars)

    candidates = screen_lambert(scenario, max_duration_s, parking_alt_m=parking_alt_m,
                                mars_periapsis_alt_m=mars_periapsis_alt_m)
    tradeoff = build_tradeoff(candidates)
    if not candidates:
        raise NoFeasibleMarsTransfer(["Lambert no encontró arcos prógrados en la ventana."], tradeoff,
                                     max_duration_s=max_duration_s)

    r_leo = earth.radius_m + parking_alt_m
    r_pm = mars.radius_m + mars_periapsis_alt_m
    re0, ve0 = _vec(earth, 0.0)
    z_ref = np.array((0.0, 0.0, 1.0))  # normal del plano orbital de la base del escenario
    counter = [0]
    reasons: list[str] = []

    # Candidatos distintos (≥ 15 días entre sí) con menor Δv estimado.
    chosen: list[MarsCandidate] = []
    for c in candidates:
        if all(abs(c.duration_s - o.duration_s) >= 15 * DAY_S for o in chosen):
            chosen.append(c)
        if len(chosen) >= candidates_to_refine:
            break

    for cand in chosen:
        t1 = cand.duration_s
        v_inf_dep = np.asarray(cand.v_inf_departure_vec)
        r_hat, v_hat, v_p = departure_perigee_state(v_inf_dep, earth.mu_m3_s2, r_leo, z_ref)
        pos0 = re0 + r_leo * r_hat
        v0 = ve0 + v_p * v_hat
        rp_hat = arrival_periapsis_direction(np.asarray(cand.v_inf_arrival_vec), mars.mu_m3_s2, r_pm, z_ref)
        target = lambda t, rp_hat=rp_hat: np.asarray(mars.pos(t)) + r_pm * rp_hat  # noqa: E731

        ok, v0_opt, sol, err = _shoot(bodies, pos0, v0, t1, target, counter=counter, tol_m=ARRIVAL_TOLERANCE_M)
        if not ok or sol is None:
            reasons.append(f"{t1 / DAY_S:.0f} días: el disparo N-cuerpos no convergió (error {err / 1000:.0f} km).")
            continue

        alt_min, t_min = _min_body_altitude(sol, mars, max(0.0, t1 - 10 * DAY_S), t1, n=400)
        if alt_min < 0.5 * mars_periapsis_alt_m:
            reasons.append(f"{t1 / DAY_S:.0f} días: periapsis marciano demasiado bajo ({alt_min / 1000:.0f} km).")
            continue

        # Δv medidos sobre la trayectoria propagada.
        v_rel0 = v0_opt - ve0
        r_unit = r_hat
        tangential = v_rel0 - float(np.dot(v_rel0, r_unit)) * r_unit
        v_circ = math.sqrt(earth.mu_m3_s2 / r_leo) * _unit(tangential)
        tmi = float(np.linalg.norm(v_rel0 - v_circ))
        y_min = sol.sol(t_min)
        rel_r = np.asarray(y_min[:3]) - np.asarray(mars.pos(t_min))
        rel_v = np.asarray(y_min[3:]) - np.asarray(mars.velocity(t_min))
        r_p_actual = float(np.linalg.norm(rel_r))
        moi = float(np.linalg.norm(rel_v)) - math.sqrt(mars.mu_m3_s2 / r_p_actual)
        v_inf_arr_actual = math.sqrt(max(0.0, float(rel_v @ rel_v) - 2.0 * mars.mu_m3_s2 / r_p_actual))
        total = tmi + moi
        return MarsTransferResult(
            scenario=scenario, duration_s=t1, tmi_delta_v_m_s=tmi, moi_delta_v_m_s=moi,
            total_delta_v_m_s=total, estimated_total_delta_v_m_s=cand.total_delta_v_m_s,
            v_inf_departure_m_s=cand.v_inf_departure_m_s, v_inf_arrival_m_s=v_inf_arr_actual,
            min_mars_altitude_m=alt_min, min_mars_altitude_t_s=t_min, arrival_error_m=err,
            parking_alt_m=parking_alt_m, mars_periapsis_alt_m=mars_periapsis_alt_m, mass_kg=mass_kg,
            propellant=estimate_propellant(mass_kg, total, isp_s), tradeoff=tradeoff,
            candidates_evaluated=len(candidates), propagations_run=counter[0],
            _segments=((0.0, t1, sol),),
        )

    raise NoFeasibleMarsTransfer(reasons, tradeoff, max_duration_s=max_duration_s)
