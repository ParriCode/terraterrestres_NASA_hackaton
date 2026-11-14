"""Integrador RK2 explicito del punto medio y eventos de impacto (contrato v1).

Escenario: Tierra-Luna, una nave de prueba, solo gravedad; sin maniobras.
Devuelve (samples, events, SimulationStatus) sin modificar el dominio comun.
"""

import math
from collections.abc import Sequence

from app.data.scenarios import Scenario
from app.models.domain import (
    CelestialBody,
    Event,
    EventType,
    SimulationConfig,
    SimulationStatus,
    SpacecraftState,
    TrajectorySample,
    Vec3,
)
from app.physics.dynamics import get_body_position_m, state_derivative
from app.physics.events import find_colliding_body, segment_min_distance_sq
from app.physics.gravity import GravityError

# Limites internos de seguridad (no son campos nuevos de SimulationConfig).
_MAX_STEP_RETRIES = 48
_MIN_STEP_S = 1e-6
_IMPACT_TIME_TOLERANCE_S = 1e-3


def vec_add(a: Vec3, b: Vec3) -> Vec3:
    """Suma de dos vectores 3D."""
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vec_scale(v: Vec3, scalar: float) -> Vec3:
    """Producto de un vector 3D por un escalar."""
    return (v[0] * scalar, v[1] * scalar, v[2] * scalar)


def _norm(v: Vec3) -> float:
    return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)


def _valid_state(state: SpacecraftState) -> bool:
    return all(
        math.isfinite(component)
        for vector in (state.position_m, state.velocity_m_s)
        for component in vector
    )


def rk2_step(
    t_s: float,
    state: SpacecraftState,
    step_s: float,
    scenario: Scenario,
) -> SpacecraftState:
    """Un paso RK2 del punto medio, consultando cuerpos en t y t+h/2."""
    if not math.isfinite(t_s) or t_s < 0:
        raise ValueError("Invalid simulation time")
    if not math.isfinite(step_s) or step_s <= 0 or t_s + step_s == t_s:
        raise ValueError("Invalid integration step")
    if not _valid_state(state):
        raise ValueError("Invalid spacecraft state")

    dr1, dv1 = state_derivative(t_s, state, scenario)
    half_step = 0.5 * step_s
    midpoint_state = SpacecraftState(
        position_m=vec_add(state.position_m, vec_scale(dr1, half_step)),
        velocity_m_s=vec_add(state.velocity_m_s, vec_scale(dv1, half_step)),
    )
    dr2, dv2 = state_derivative(t_s + half_step, midpoint_state, scenario)
    next_state = SpacecraftState(
        position_m=vec_add(state.position_m, vec_scale(dr2, step_s)),
        velocity_m_s=vec_add(state.velocity_m_s, vec_scale(dv2, step_s)),
    )
    if not _valid_state(next_state):
        raise ArithmeticError("RK2 produced a non-finite state")
    return next_state


def _body_positions_at(
    scenario: Scenario,
    t_s: float,
    bodies: Sequence[CelestialBody] | None = None,
) -> dict[str, Vec3]:
    """Usa el mismo proveedor de posiciones que dynamics.py."""
    if bodies is None:
        bodies = scenario.get_bodies()
    result: dict[str, Vec3] = {}
    for body in bodies:
        position = get_body_position_m(scenario, body, t_s)
        if len(position) != 3 or not all(math.isfinite(v) for v in position):
            raise GravityError(f"Invalid ephemeris position for {body.id} at t={t_s}")
        result[body.id] = position
    return result


def _safe_step_s(
    t_s: float,
    state: SpacecraftState,
    step_s: float,
    body_positions: dict[str, Vec3],
    bodies: Sequence[CelestialBody],
    scenario: Scenario,
) -> float:
    """Limita saltos excesivos que podrian atravesar una esfera entre muestras.

    El valor solicitado sigue siendo el MAXIMO; cerca de un cuerpo se subdivide
    por escala de movimiento relativo y por escala gravitatoria. No es un
    integrador de tolerancia adaptativa ni una garantia matematica absoluta.
    """
    future_positions = _body_positions_at(scenario, t_s + step_s, bodies)
    limit = step_s
    for body in bodies:
        pos = body_positions[body.id]
        next_pos = future_positions[body.id]
        relative_position = tuple(s - b for s, b in zip(state.position_m, pos))
        distance = _norm(relative_position)
        if not math.isfinite(distance) or distance <= 0:
            raise GravityError(f"Invalid distance to {body.id}")

        body_velocity = tuple((b - a) / step_s for a, b in zip(pos, next_pos))
        relative_velocity = tuple(s - b for s, b in zip(state.velocity_m_s, body_velocity))
        speed = _norm(relative_velocity)
        if not math.isfinite(speed):
            raise GravityError("Invalid relative speed")
        if speed > 0:
            limit = min(limit, 0.25 * distance / speed)
        if body.mu_m3_s2 > 0:
            limit = min(limit, 0.15 * math.sqrt(distance**3 / body.mu_m3_s2))
    return limit


def _refine_collision(
    t_s: float,
    state: SpacecraftState,
    step_s: float,
    end_state: SpacecraftState,
    colliding_body: CelestialBody,
    bodies: Sequence[CelestialBody],
    scenario: Scenario,
) -> tuple[float, SpacecraftState, dict[str, Vec3]]:
    """Biseccion temporal: el inicio es exterior y el final es interior.

    En todo momento RK2 recibe DURACION desde t_s, no un tiempo absoluto.
    """
    low_s = 0.0
    high_s = step_s
    hit_state = end_state
    for _ in range(80):
        if high_s - low_s <= _IMPACT_TIME_TOLERANCE_S:
            break
        middle_s = low_s + (high_s - low_s) * 0.5
        mid_state = rk2_step(t_s, state, middle_s, scenario)
        mid_t_s = t_s + middle_s
        mid_pos = get_body_position_m(scenario, colliding_body, mid_t_s)
        delta = tuple(a - b for a, b in zip(mid_state.position_m, mid_pos))
        if sum(value * value for value in delta) <= colliding_body.radius_m**2:
            high_s = middle_s
            hit_state = mid_state
        else:
            low_s = middle_s
    hit_t_s = t_s + high_s
    return hit_t_s, hit_state, _body_positions_at(scenario, hit_t_s, bodies)


def _maybe_hidden_collision(
    state: SpacecraftState,
    next_state: SpacecraftState,
    positions: dict[str, Vec3],
    next_positions: dict[str, Vec3],
    bodies: Sequence[CelestialBody],
) -> bool:
    """Detecta una cuerda que atraviesa una esfera pese a extremos exteriores."""
    return any(
        segment_min_distance_sq(
            state.position_m,
            next_state.position_m,
            positions[body.id],
            next_positions[body.id],
        ) <= body.radius_m**2
        for body in bodies
    )


def integrate(
    config: SimulationConfig,
    scenario: Scenario,
) -> tuple[list[TrajectorySample], list[Event], SimulationStatus]:
    """Propaga la trayectoria y detiene la simulacion al primer impacto.

    Garantias del contrato v1:
    - primera muestra t=0; tiempos estrictamente crecientes;
    - cada muestra contiene posiciones planetarias para SU tiempo;
    - ultimo paso acaba exactamente en duration_s si no hay impacto;
    - ultimo punto en impacto + Event(type='collision') + status COLLISION;
    - errores numericos nunca agregan muestras invalidas.
    """
    if not math.isfinite(config.duration_s) or config.duration_s <= 0:
        raise ValueError("Invalid simulation duration")
    if not math.isfinite(config.step_s) or config.step_s <= 0:
        raise ValueError("Invalid integration step")
    if not _valid_state(config.initial_state):
        raise ValueError("Invalid initial state")

    bodies = list(scenario.get_bodies())
    ids = [body.id for body in bodies]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate celestial body identifiers")
    if not bodies:
        raise ValueError("Scenario has no celestial bodies")

    t_s = 0.0
    state = config.initial_state
    # Sin efemérides válidas ni siquiera la muestra inicial es fiable.
    try:
        positions = _body_positions_at(scenario, t_s, bodies)
    except (GravityError, ArithmeticError, ValueError, OverflowError):
        return [], [], SimulationStatus.NUMERICAL_ERROR

    samples = [TrajectorySample(t_s=t_s, spacecraft=state, body_positions_m=positions)]
    events: list[Event] = []

    collided = find_colliding_body(state, positions, bodies)
    if collided is not None:
        events.append(Event(type=EventType.COLLISION, t_s=t_s, body_id=collided.id,
                            position_m=state.position_m))
        return samples, events, SimulationStatus.COLLISION

    while t_s < config.duration_s:
        remaining_s = config.duration_s - t_s
        dt = min(config.step_s, remaining_s)
        try:
            dt = _safe_step_s(t_s, state, dt, positions, bodies, scenario)
        except (GravityError, ValueError, ArithmeticError, OverflowError):
            return samples, events, SimulationStatus.NUMERICAL_ERROR
        if not math.isfinite(dt) or dt <= 0 or t_s + dt == t_s:
            return samples, events, SimulationStatus.NUMERICAL_ERROR

        accepted = False
        # El usuario puede pedir pasos inferiores a 1 microsegundo; el limite
        # solo frena subdivisiones patologicas durante reintentos.
        retry_floor_s = min(_MIN_STEP_S, config.step_s, remaining_s)
        for _ in range(_MAX_STEP_RETRIES):
            if dt < retry_floor_s or t_s + dt == t_s:
                break
            end_t_s = config.duration_s if dt == remaining_s else t_s + dt
            # Reducir al avance representable para evitar diferencias de redondeo.
            dt = end_t_s - t_s
            if dt <= 0:
                break
            try:
                next_state = rk2_step(t_s, state, dt, scenario)
                next_positions = _body_positions_at(scenario, end_t_s, bodies)
                collided = find_colliding_body(next_state, next_positions, bodies)

                # Si el extremo esta dentro, biseccion desde el estado exterior.
                if collided is not None:
                    hit_t_s, hit_state, hit_positions = _refine_collision(
                        t_s, state, dt, next_state, collided, bodies, scenario
                    )
                    if hit_t_s <= t_s:
                        return samples, events, SimulationStatus.NUMERICAL_ERROR
                    samples.append(TrajectorySample(
                        t_s=hit_t_s,
                        spacecraft=hit_state,
                        body_positions_m=hit_positions,
                    ))
                    events.append(Event(
                        type=EventType.COLLISION,
                        t_s=hit_t_s,
                        body_id=collided.id,
                        position_m=hit_state.position_m,
                    ))
                    return samples, events, SimulationStatus.COLLISION

                # Una nave puede ENTRAR y SALIR del cuerpo dentro del paso.
                # Si la cuerda lo cruza, repetir el calculo con medio paso.
                if _maybe_hidden_collision(state, next_state, positions, next_positions, bodies):
                    dt *= 0.5
                    continue

                # Inspeccion adicional del punto medio cerca de cualquier esfera:
                # protege contra pasos curvos que el segmento lineal no captura.
                near_body = any(
                    segment_min_distance_sq(
                        state.position_m, next_state.position_m,
                        positions[body.id], next_positions[body.id],
                    ) <= (3.0 * body.radius_m)**2
                    for body in bodies
                )
                if near_body:
                    half_state = rk2_step(t_s, state, 0.5 * dt, scenario)
                    half_t_s = t_s + 0.5 * dt
                    half_positions = _body_positions_at(scenario, half_t_s, bodies)
                    half_collided = find_colliding_body(half_state, half_positions, bodies)
                    if half_collided is not None:
                        hit_t_s, hit_state, hit_positions = _refine_collision(
                            t_s, state, 0.5 * dt, half_state,
                            half_collided, bodies, scenario
                        )
                        if hit_t_s <= t_s:
                            return samples, events, SimulationStatus.NUMERICAL_ERROR
                        samples.append(TrajectorySample(
                            t_s=hit_t_s, spacecraft=hit_state,
                            body_positions_m=hit_positions,
                        ))
                        events.append(Event(
                            type=EventType.COLLISION, t_s=hit_t_s,
                            body_id=half_collided.id, position_m=hit_state.position_m,
                        ))
                        return samples, events, SimulationStatus.COLLISION

                samples.append(TrajectorySample(
                    t_s=end_t_s, spacecraft=next_state,
                    body_positions_m=next_positions,
                ))
                state = next_state
                positions = next_positions
                t_s = end_t_s
                accepted = True
                break

            except (GravityError, ArithmeticError, ValueError, OverflowError):
                # Un punto medio dentro de un cuerpo no puede evaluarse. Con un
                # paso menor, normalmente encontramos el impacto en el extremo.
                dt *= 0.5

        if not accepted:
            return samples, events, SimulationStatus.NUMERICAL_ERROR

    return samples, events, SimulationStatus.COMPLETED
