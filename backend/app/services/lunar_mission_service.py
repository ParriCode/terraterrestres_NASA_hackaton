"""Misión Tierra -> órbita lunar -> entorno terrestre, con impulsos explícitos.

No es una trayectoria de retorno libre: insertarse y salir de órbita requiere
maniobras. La física se integra en el mismo modelo planar Tierra-Luna que el
endpoint de transferencias; la Luna se mueve según las efemérides de Horizons.
Se rechazan candidatos que no cumplan las comprobaciones geométricas.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import time
from typing import Any

import numpy as np
from scipy.optimize import brentq

from app.data.scenarios import PlanarScenario
from app.physics.lambert import LambertError, solve_lambert
from app.physics.propagation import propagate_planar
from app.services.transfer_service import (
    TransferNotFoundError,
    _build_fast_shooting_residual,
    _solve_planar_shooting_fast,
    optimize_transfer,
)

SECONDS_DAY = 86400.0
EARTH_ENTRY_ALTITUDE_M = 120_000.0  # interfaz de entrada; no simula descenso ni aterrizaje


def _entry_radius_m(scenario: Any) -> float:
    """Radio absoluto del objetivo a partir del radio terrestre del escenario."""
    return float(scenario.bodies['earth'].radius_m) + EARTH_ENTRY_ALTITUDE_M
MIN_ORBIT_CLEARANCE_M = 20_000.0


@dataclass(frozen=True)
class LunarManeuver:
    phase: str
    t_s: float
    delta_v_m_s: float
    before_m_s: tuple[float, float, float]
    after_m_s: tuple[float, float, float]


def _relative(body: Any, t: float, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    position = np.array(body.pos(t)[:2], dtype=float)
    velocity = np.array(body.speed(t)[:2], dtype=float)
    return y[:2] - position, y[2:4] - velocity


def lunar_orbit_injection(scenario: Any, t: float, arrival_state: np.ndarray, orbit_radius_m: float):
    """Circulariza una llegada lunar a radio dado (impulso, no vuelo libre).

    Se preserva la posición y se cambia la velocidad, eligiendo sentido
    pro/retrógrado que requiera el menor delta-v. Retorna nuevo estado, Δv.
    """
    moon = scenario.bodies['moon']
    r, v = _relative(moon, t, arrival_state)
    norm_r = float(np.linalg.norm(r))
    if abs(norm_r - orbit_radius_m) > 100.0:
        raise TransferNotFoundError('La llegada no está en la altitud de inserción lunar solicitada.')
    if np.dot(r, v) >= 0:
        raise TransferNotFoundError('La nave no se está aproximando a la Luna durante la inserción.')
    tangent = np.array([-r[1], r[0]]) / norm_r
    speed = math.sqrt(moon.mu_m3_s2 / norm_r)
    mv = np.array(moon.speed(t)[:2], dtype=float)
    options = [mv + sign * speed * tangent for sign in (-1, 1)]
    new_v = min(options, key=lambda z: np.linalg.norm(z - arrival_state[2:4]))
    dv = float(np.linalg.norm(new_v - arrival_state[2:4]))
    return np.array([arrival_state[0], arrival_state[1], new_v[0], new_v[1]]), dv


def _find_orbit_entry(transfer: Any, altitude_m: float) -> tuple[float, np.ndarray]:
    moon = transfer.scenario.bodies['moon']
    radius = moon.radius_m + altitude_m
    solution = transfer._solution
    end = float(transfer.t1_s)

    def clearance(t: float) -> float:
        state = np.asarray(solution.sol(t), dtype=float)
        return float(np.linalg.norm(state[:2] - np.asarray(moon.pos(t)[:2]))) - radius

    # Buscar el último cruce ENTRANTE en las 12 horas previas al contacto lunar.
    # El paso de 30 s permite detectar el cruce incluso a velocidad alta.
    t_right = end
    f_right = clearance(t_right)
    for _ in range(int(min(12 * 3600, end) / 30) + 1):
        t_left = max(0.0, t_right - 30.0)
        f_left = clearance(t_left)
        if f_left >= 0.0 and f_right <= 0.0:
            t = float(brentq(clearance, t_left, t_right, xtol=1e-6))
            return t, np.asarray(solution.sol(t), dtype=float)
        if t_left == 0.0:
            break
        t_right, f_right = t_left, f_left
    raise TransferNotFoundError('No se ha detectado un cruce entrante de la órbita lunar elegida.')


def _checked_arc(scenario: Any, solution: Any, t0: float, t1: float, phase: str):
    if not solution.success or abs(float(solution.t[-1]) - t1) > 1e-5:
        raise TransferNotFoundError(f'La fase {phase} no se pudo propagar por completo.')
    # Los eventos del integrador detectan penetraciones entre las muestras
    # utilizadas después para comprobar el margen de seguridad.
    if getattr(solution, 't_events', None) is not None:
        for body, hits in zip(scenario.get_bodies(), solution.t_events):
            if len(hits):
                raise TransferNotFoundError(f'Impacto con {body.id} durante {phase}.')
    times = np.linspace(t0, t1, 240)
    positions = solution.sol(times)[:2].T
    for key in ('moon', 'earth'):
        body = scenario.bodies[key]
        pos_array = getattr(body, 'pos_array', None)
        centers = pos_array(times)[:, :2] if callable(pos_array) else np.array([body.pos(float(t))[:2] for t in times])
        smallest = float(np.min(np.linalg.norm(positions - centers, axis=1)))
        if smallest < body.radius_m + (MIN_ORBIT_CLEARANCE_M if key == 'moon' else 0.0):
            raise TransferNotFoundError(f'Colisión o margen insuficiente con {key} durante {phase}.')


def _direct_return_candidates(scenario: Any, t_depart: float, t_limit: float,
                              state: np.ndarray, *, deadline: float, objective: str):
    """Busca un cruce entrante a 120 km de altitud terrestre ANTES del límite.

    Los impulsos se evalúan en el modelo gravitatorio real, sin exigir
    artificialmente que la nave llegue justo el último día elegido.
    Ningún candidato se declara válido sin propagación fina y detección de
    eventos de impacto. La búsqueda sigue siendo acotada, no óptima global.
    """
    earth, moon = scenario.bodies['earth'], scenario.bodies['moon']
    entry_radius_m = _entry_radius_m(scenario)
    earth_at_depart = np.asarray(earth.pos(t_depart)[:2], dtype=float)
    moon_velocity = np.asarray(moon.speed(t_depart)[:2], dtype=float)
    to_earth = earth_at_depart - state[:2]
    to_earth /= np.linalg.norm(to_earth)
    transverse = np.array([-to_earth[1], to_earth[0]])
    best = None
    best_score = float('inf')
    attempts = 0
    # Primero direcciones próximas a Tierra; después alternativas oblicuas.
    for deg in (0, -20, 20, -45, 45, -70, 70, -100, 100, 180):
        for speed in (2600., 3100., 2200., 3600.):
            if time.monotonic() >= deadline:
                return best, attempts
            attempts += 1
            angle = math.radians(deg)
            direction = math.cos(angle) * to_earth + math.sin(angle) * transverse
            v = moon_velocity + speed * direction
            try:
                rough = propagate_planar(
                    scenario, state[:2], v, t_depart, t_limit,
                    events=True, dense_output=False, rtol=2e-8, atol=1e-4,
                    budget_check=lambda: _check_deadline(deadline),
                    stop_at_earth_radius_m=entry_radius_m,
                )
                if not len(rough.t_events[-1]):
                    continue
                # Refinar únicamente las candidatas que realmente regresaron.
                fine = propagate_planar(
                    scenario, state[:2], v, t_depart, t_limit,
                    events=True, dense_output=True, rtol=1e-10, atol=1e-6,
                    budget_check=lambda: _check_deadline(deadline),
                    stop_at_earth_radius_m=entry_radius_m,
                )
                if not len(fine.t_events[-1]):
                    continue
                arrival_t = float(fine.t_events[-1][0])
                _checked_arc(scenario, fine, t_depart, arrival_t, 'regreso')
                r_end, v_end = _relative(earth, arrival_t, np.asarray(fine.y[:, -1]))
                if np.dot(r_end, v_end) >= 0:
                    continue
                if abs(np.linalg.norm(r_end) - entry_radius_m) > 50_000.:
                    continue
                dv = float(np.linalg.norm(v - state[2:4]))
                if objective == 'energia':
                    score = dv**2
                else:
                    path = fine.sol(np.linspace(t_depart, arrival_t, 200))[:2].T
                    score = float(np.linalg.norm(np.diff(path, axis=0), axis=1).sum())
                if score >= best_score:
                    continue
                epos = np.asarray(earth.pos(arrival_t)[:2], dtype=float)
                mpos = np.asarray(moon.pos(arrival_t)[:2], dtype=float)
                radial = mpos - epos
                radial /= np.linalg.norm(radial)
                arrival_vector = r_end / np.linalg.norm(r_end)
                arrival_deg = math.degrees(math.atan2(
                    radial[0] * arrival_vector[1] - radial[1] * arrival_vector[0],
                    np.dot(radial, arrival_vector),
                ))
                best = (fine, v, dv, arrival_deg, arrival_t)
                best_score = score
            except (RuntimeError, ValueError, ArithmeticError, TimeoutError):
                continue
    return best, attempts


def _return_solution(scenario: Any, t_depart: float, t_end: float, state: np.ndarray, *,
                     deadline: float, objective: str):
    earth, moon = scenario.bodies['earth'], scenario.bodies['moon']
    entry_radius_m = _entry_radius_m(scenario)
    e_end = np.array(earth.pos(t_end)[:2])
    m_end = np.array(moon.pos(t_end)[:2])
    radial = (m_end - e_end) / np.linalg.norm(m_end - e_end)
    e_depart = np.array(earth.pos(t_depart)[:2])
    earth_vel = np.array(earth.speed(t_depart)[:2])
    moon_vel = np.array(moon.speed(t_depart)[:2])
    start_rel = state[:2] - e_depart
    flight_s = t_end - t_depart
    if flight_s <= 0:
        raise TransferNotFoundError('No queda tiempo para el regreso a la Tierra.')

    # La duración del formulario se interpreta como tiempo MÁXIMO de misión.
    # Una nave que alcanza el entorno terrestre antes es un retorno válido.
    quick_deadline = min(deadline, time.monotonic() + 35.0)
    direct, direct_attempts = _direct_return_candidates(
        scenario, t_depart, t_end, state,
        deadline=quick_deadline, objective=objective,
    )
    if direct is not None:
        return direct

    best = None
    best_score = float('inf')
    # Fallback: disparo hacia la interfaz de entrada, al final del plazo.
    for deg in (0, -45, 45, -90, 90, 180):
        if time.monotonic() >= deadline:
            break
        angle = math.radians(deg)
        unit = radial * math.cos(angle) + np.array([-radial[1], radial[0]]) * math.sin(angle)
        target = e_end + entry_radius_m * unit
        residual = _build_fast_shooting_residual(
            scenario,
            (float(state[0]), float(state[1]), 0.0),
            (float(target[0]), float(target[1]), 0.0),
            t_depart, t_end,
            budget_check=lambda: _check_deadline(deadline),
        )
        if residual is None:
            def residual(velocity):
                _check_deadline(deadline)
                sol = propagate_planar(scenario, state[:2], velocity, t_depart, t_end,
                                       events=False, dense_output=False, rtol=1e-7, atol=1e-4)
                return float(sol.y[0, -1] - target[0]), float(sol.y[1, -1] - target[1]), 0.0
        seeds = []
        # Semillas Lambert en el problema auxiliar de dos cuerpos (Tierra).
        for prograde in (True, False):
            try:
                lam = solve_lambert(
                    (float(start_rel[0]), float(start_rel[1]), 0.0),
                    (float(entry_radius_m * unit[0]), float(entry_radius_m * unit[1]), 0.0),
                    flight_s, earth.mu_m3_s2, prograde=prograde,
                )
                seeds.append(tuple(float(v) for v in (
                    lam.departure_velocity_m_s[0] + earth_vel[0],
                    lam.departure_velocity_m_s[1] + earth_vel[1], 0.0,
                )))
            except (LambertError, ValueError, ArithmeticError):
                pass
        toward = (e_depart - state[:2]) / np.linalg.norm(e_depart - state[:2])
        seeds.extend([
            (float(moon_vel[0] + toward[0] * s), float(moon_vel[1] + toward[1] * s), 0.0)
            for s in (2200.0, 2800.0)
        ])
        for guess in seeds:
            if time.monotonic() >= deadline:
                break
            try:
                shot = _solve_planar_shooting_fast(
                    guess, residual, arrival_tolerance_m=50_000.0,
                    max_evaluations=32,
                )
                if not shot.converged:
                    continue
                v = np.array(shot.initial_velocity_m_s[:2])
                # Propagación con eventos y precisión superior a las evaluaciones.
                sol = propagate_planar(scenario, state[:2], v, t_depart, t_end,
                                       events=True, dense_output=True, rtol=1e-10, atol=1e-6)
                if np.linalg.norm(sol.y[:2, -1] - target) > 50_000.0:
                    continue
                _checked_arc(scenario, sol, t_depart, t_end, 'regreso')
                r_end, v_end = _relative(earth, t_end, np.asarray(sol.y[:, -1]))
                if np.dot(r_end, v_end) >= 0:
                    continue
                # Sin entrada temprana en la esfera de retorno.
                probe = np.linspace(t_depart, t_end, 180)[:-1]
                ep = getattr(earth, 'pos_array', None)
                centers = ep(probe)[:, :2] if callable(ep) else np.array([earth.pos(float(t))[:2] for t in probe])
                if np.any(np.linalg.norm(sol.sol(probe)[:2].T - centers, axis=1) < entry_radius_m - 10_000.0):
                    continue
                dv = float(np.linalg.norm(v - state[2:4]))
                # Respetar el objetivo: energía de maniobra o distancia recorrida.
                if objective == 'energia':
                    score = dv ** 2
                else:
                    traj = sol.sol(np.linspace(t_depart, t_end, 220))[:2].T
                    score = float(np.linalg.norm(np.diff(traj, axis=0), axis=1).sum())
                if score < best_score:
                    best, best_score = (sol, v, dv, deg), score
            except (RuntimeError, ValueError, ArithmeticError, TimeoutError):
                continue
    if best is None:
        raise TransferNotFoundError(
            f'No se encontró un retorno validado antes del límite de tiempo. '
            f'Se evaluaron {direct_attempts} impulsos directos y alternativas de disparo. '
            'Esto no demuestra imposibilidad física; prueba otra fecha, duración o altitud.'
        )
    return (*best, t_end)


def _check_deadline(deadline: float):
    if time.monotonic() >= deadline:
        raise TimeoutError('Tiempo de búsqueda agotado.')


def _serialize_phase(scenario, solution, a: float, b: float, count: int, *, include_start: bool):
    if count < 2:
        count = 2
    t = np.linspace(a, b, count)
    if not include_start:
        t = t[1:]
    states = solution.sol(t)
    pos_tracks = {}
    for key, body in scenario.bodies.items():
        pos_array = getattr(body, 'pos_array', None)
        pos_tracks[key] = pos_array(t) if callable(pos_array) else np.array([body.pos(float(x)) for x in t])
    return [
        {
            't_s': float(t[i]),
            'position_m': [float(states[0, i]), float(states[1, i]), 0.0],
            'velocity_m_s': [float(states[2, i]), float(states[3, i]), 0.0],
            'body_positions_m': {k: [float(pos_tracks[k][i, 0]), float(pos_tracks[k][i, 1]), 0.0] for k in scenario.bodies},
        }
        for i in range(len(t))
    ]


def design_lunar_orbit_return(
    date: datetime,
    duration_s: float,
    *,
    mass_kg: float,
    objective: str,
    samples: int = 400,
    orbit_altitude_km: float = 100.0,
    lunar_revolutions: int = 1,
    launch_angle_deg: float = 90.0,
    time_budget_s: float = 100.0,
) -> dict:
    """Busca 3 arcos reales. Devuelve respuesta solo tras validar retorno.

    No modela motores, combustible ni reentrada. Los impulsos se informan como
    delta-v requerido, nunca como consumo de propelente calculado.
    """
    if not 4 * SECONDS_DAY <= duration_s <= 30 * SECONDS_DAY:
        raise ValueError('Para orbitar y regresar, la duración total debe estar entre 4 y 30 días.')
    if not 50.0 <= orbit_altitude_km <= 500.0:
        raise ValueError('La órbita lunar debe estar entre 50 y 500 km de altitud.')
    if isinstance(lunar_revolutions, bool) or not isinstance(lunar_revolutions, int) or not 1 <= lunar_revolutions <= 100:
        raise ValueError('lunar_revolutions debe ser un entero entre 1 y 100.')
    if not 100 <= samples <= 4000 or not mass_kg > 0 or not math.isfinite(mass_kg):
        raise ValueError('Se requieren entre 100 y 4000 muestras y una masa positiva.')
    if samples < 12 * lunar_revolutions + 60:
        raise ValueError('Aumenta las muestras para representar todas las revoluciones.')
    if objective not in ('energia', 'distancia'):
        raise ValueError('Objetivo inválido.')
    deadline = time.monotonic() + time_budget_s
    outbound_duration = duration_s * 0.30
    # Se usan las efemérides reales en ambos cálculos, con el mismo plano inicial.
    outbound_optimized = optimize_transfer(
        date, outbound_duration, mass_kg=mass_kg, objective=objective,
        launch_angle_deg=launch_angle_deg,
        time_budget_s=min(40.0, time_budget_s * .45),
    )
    outbound = outbound_optimized.transfer
    scenario = PlanarScenario(date, duration_s)
    entry_radius_m = _entry_radius_m(scenario)
    moon = scenario.bodies['moon']
    r_orbit = moon.radius_m + orbit_altitude_km * 1000
    t_capture, y_capture = _find_orbit_entry(outbound, orbit_altitude_km * 1000)
    # La escena completa y la ida comparten origen y base ICRF inicial.
    if not np.allclose(outbound.scenario.basis_icrf, scenario.basis_icrf, atol=1e-10):
        raise TransferNotFoundError('Incompatibilidad de marcos ICRF entre las fases.')
    state_orbit, dv_capture = lunar_orbit_injection(scenario, t_capture, y_capture, r_orbit)
    period = 2 * math.pi * math.sqrt(r_orbit ** 3 / moon.mu_m3_s2)
    t_depart = t_capture + period * lunar_revolutions
    if t_depart >= duration_s - SECONDS_DAY:
        raise TransferNotFoundError('Duración insuficiente para la fase de retorno.')
    lunar_solution = propagate_planar(scenario, state_orbit[:2], state_orbit[2:4], t_capture, t_depart,
                                      events=True, dense_output=True, rtol=1e-10, atol=1e-6)
    _checked_arc(scenario, lunar_solution, t_capture, t_depart, 'órbita lunar')
    moon_cent = np.array(moon.pos(t_depart)[:2])
    final_orbit_radius = np.linalg.norm(lunar_solution.y[:2, -1] - moon_cent)
    orbit_check_times = np.linspace(t_capture, t_depart, max(220, 24 * lunar_revolutions))
    moon_positions = np.array([moon.pos(float(t))[:2] for t in orbit_check_times])
    orbit_positions = lunar_solution.sol(orbit_check_times)[:2].T - moon_positions
    orbit_angles = np.unwrap(np.arctan2(orbit_positions[:, 1], orbit_positions[:, 0]))
    actual_revolutions = abs(float(orbit_angles[-1] - orbit_angles[0])) / (2 * math.pi)
    if abs(actual_revolutions - lunar_revolutions) > 0.15 * lunar_revolutions:
        raise TransferNotFoundError('No se completó el número de órbitas lunares solicitado.')
    if abs(final_orbit_radius - r_orbit) > r_orbit * 0.15:
        raise TransferNotFoundError('La órbita lunar no se mantuvo estable durante la revolución.')

    state_depart = np.asarray(lunar_solution.y[:, -1], dtype=float)
    if time.monotonic() >= deadline:
        raise TransferNotFoundError('El tiempo de búsqueda se agotó antes de diseñar el retorno.')
    sol_return, v_return, dv_return, arrival_direction, return_arrival_t = _return_solution(
        scenario, t_depart, duration_s, state_depart,
        deadline=deadline, objective=objective,
    )
    capture_prev = tuple(float(v) for v in y_capture[2:4]) + (0.0,)
    capture_after = tuple(float(v) for v in state_orbit[2:4]) + (0.0,)
    return_prev = tuple(float(v) for v in state_depart[2:4]) + (0.0,)
    return_after = tuple(float(v) for v in v_return) + (0.0,)
    maneuvers = [
        LunarManeuver('inserción_orbital', t_capture, dv_capture, capture_prev, capture_after),
        LunarManeuver('inyección_retorno', t_depart, dv_return, return_prev, return_after),
    ]
    # Respuesta compatible con TransferResponse: muestras de las 3 fases.
    actual_duration = return_arrival_t
    # Conservar el total de muestras, dando prioridad al tramo lunar.
    n_moon = min(samples - 60, max(36, 12 * lunar_revolutions, round(samples * (t_depart - t_capture) / actual_duration)))
    remaining = samples - n_moon
    n_out = min(remaining - 30, max(30, round(remaining * t_capture / max(actual_duration - (t_depart - t_capture), 1))))
    n_return = samples - n_out - n_moon
    # Eliminar el estado anterior a cada impulso en el mismo instante. Los
    # eventos exponen ambas velocidades; la serie de muestras crece estrictamente.
    out_times = np.linspace(0, t_capture, n_out)
    out_times[-1] = max(0.0, t_capture - .001)
    outbound_samples = _serialize_phase(outbound.scenario, outbound._solution, 0, float(out_times[-1]), n_out, include_start=True)
    orbit_samples = _serialize_phase(scenario, lunar_solution, t_capture, t_depart - .001, n_moon, include_start=True)
    return_samples = _serialize_phase(scenario, sol_return, t_depart, actual_duration, n_return, include_start=True)
    all_samples = outbound_samples + orbit_samples + return_samples
    # Distancia recorrida respecto al centro de Tierra, por continuidad temporal.
    ship = np.array([s['position_m'][:2] for s in all_samples])
    earths = np.array([s['body_positions_m']['earth'][:2] for s in all_samples])
    path_len = float(np.linalg.norm(np.diff(ship - earths, axis=0), axis=1).sum())
    earth_body = scenario.bodies['earth']
    e_end = np.array(earth_body.pos(actual_duration)[:2])
    earth_speed = np.array(earth_body.speed(actual_duration)[:2])
    state_at_entry = np.asarray(sol_return.y[:, -1], dtype=float)
    earth_relative_r = state_at_entry[:2] - e_end
    earth_relative_v = state_at_entry[2:4] - earth_speed
    entry_speed_m_s = float(np.linalg.norm(earth_relative_v))
    inbound = bool(np.dot(earth_relative_r, earth_relative_v) < 0)
    if not inbound or abs(np.linalg.norm(earth_relative_r) - entry_radius_m) > 50_000.:
        raise TransferNotFoundError('No se verificó la llegada entrante a 120 km de altitud terrestre.')
    arrival_error = abs(float(np.linalg.norm(sol_return.y[:2, -1] - e_end)) - entry_radius_m)
    return {
        'source': 'NASA/JPL Horizons', 'date': date,
        'frame': 'earth_moon_barycentric_initial_orbital_plane',
        'basis_icrf': scenario.basis_icrf.tolist(),
        'objective': objective, 'mass_kg': mass_kg,
        'arrival_angle_deg': outbound_optimized.arrival_angle_deg,  # Geometría de la llegada a la Luna.
        'initial_velocity_m_s': list(outbound.initial_velocity_m_s),
        'launch_speed_m_s': outbound.launch_speed_m_s,
        'launch_energy_j': outbound.launch_energy_j,
        'path_length_m': path_len, 'arrival_error_m': arrival_error,
        'duration_s': actual_duration,
        'requested_duration_s': duration_s,
        'bodies': {k: {'name': body.name, 'radius_m': body.radius_m} for k, body in scenario.bodies.items()},
        'samples': all_samples,
        'mission_mode': 'lunar_orbit_return',
        'return_interface_radius_m': entry_radius_m,
        'earth_entry': {
            'altitude_km': EARTH_ENTRY_ALTITUDE_M / 1000.0,
            'relative_speed_m_s': entry_speed_m_s,
            'inbound': inbound,
            'validated': True,
            'landing_simulated': False,
        },
        'lunar_orbit': {
            'altitude_km': orbit_altitude_km,
            'revolutions': lunar_revolutions,
            'actual_revolutions': actual_revolutions,
            'orbit_insertion_t_s': t_capture,
            'orbit_departure_t_s': t_depart,
            'orbital_period_s': period,
            'return_arrival_direction_deg': arrival_direction,
            'return_arrival_t_s': actual_duration,
            'verified_return': True,
        },
        'maneuvers': [m.__dict__ for m in maneuvers],
        'total_maneuver_delta_v_m_s': dv_capture + dv_return,
        'model_limitations': [
            'La optimización es por etapas, no una búsqueda conjunta global de todos los impulsos.',
            'Modelo gravitatorio planar Tierra-Luna con efemérides prescritas de NASA/JPL.',
            'Inserción y salida lunares mediante impulsos ideales; sin presupuesto de combustible.',
            'Regreso validado a 120 km de altitud sobre Tierra; NO se simula atmósfera ni aterrizaje.',
            'Búsqueda acotada: no se garantiza óptimo global.',
            'La duración introducida es un límite máximo: el regreso puede completarse antes.',
        ],
    }
