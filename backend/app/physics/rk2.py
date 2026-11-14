"""Integrador del punto medio RK2."""

import math
from collections.abc import Sequence
from app.data.scenarios import Scenario
from app.models.domain import (
    Event,
    SimulationConfig,
    SimulationStatus,
    SpacecraftState,
    TrajectorySample,
    Vec3,
)
from app.physics.dynamics import state_derivative
from app.physics.events import (
    CollidableBody,
    find_colliding_body,
    is_collision,
    swept_collision_closest_fraction,
)
from app.physics.gravity import GravityError

COLLISION_TIME_TOLERANCE_S = 1e-6
MAX_BISECTION_ITERATIONS = 80

"""
!Recibe dos Vec3 y hace la suma de vector
@param a Vector 1
@param b Vector 2
@return Suma de los vectores
"""
def vec_add(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[0] + b[0],
        a[1] + b[1],
        a[2] + b[2],
    )

"""
!Recibe un Vec3 y una escala
@param v Vector a reescalar
@param scalar Coeficiente de escala
@return Vector reescalado
"""
def vec_scale(v: Vec3, scalar: float) -> Vec3:
    return (
        v[0] * scalar,
        v[1] * scalar,
        v[2] * scalar,
    )

"""
!Recibe tiempo t_s, el estado actual del SpacecraftState, un paso de step_s (los segundos a avanzar) y un Scenario, calcula el próximo estado del SpacecraftState aplicando Runge-Kutta de 2 pasos
@return Nuevo estado de SpacecraftState pasado step_s desde t_s
"""
def rk2_step(
    t_s: float,
    state: SpacecraftState,
    step_s: float,
    scenario: Scenario,
) -> SpacecraftState:
    if not math.isfinite(t_s) or t_s < 0:
        raise ValueError("Invalid simulation time")

    if not math.isfinite(step_s) or step_s <= 0:
        raise ValueError("Invalid integration step")

    dr_1, dv_1 = state_derivative(
        t_s,
        state,
        scenario,
    )

    midpoint_state = SpacecraftState(
        position_m = vec_add(
            state.position_m,
            vec_scale(dr_1, step_s/2),
        ),
        velocity_m_s = vec_add(
            state.velocity_m_s,
            vec_scale(dv_1, step_s/2),
        ),
    )

    midpoint_time = t_s + step_s/2

    dr_2, dv_2 = state_derivative(
        midpoint_time,
        midpoint_state,
        scenario,
    )

    next_state = SpacecraftState(
        position_m = vec_add(
            state.position_m,
            vec_scale(dr_2, step_s),
        ),
        velocity_m_s = vec_add(
            state.velocity_m_s,
            vec_scale(dv_2, step_s),
        ),
    )

    return next_state

"""
!Dado un escenario scenario y un tiempo t_s, devuelve las posiciones de las planetas según su id
@param scenario Escenario a considerar
@param t_s Tiempo a considerar
@return Hash table de id de planeta con su posición
"""
def _body_positions_at(
    scenario: Scenario,
    t_s: float,
) -> dict[str, Vec3]:

    return {
        body_id: body.pos(t_s)
        for body_id, body in scenario.bodies.items()
    }

"""
Dado un tiempo t0, un estado inicial state0, un tiempo t y un escenario, devuelve el estado que llegaría mediante Runge-Kutta
@param t0 Tiempo inicial
@param state0 Estado inicial
@param t Tiempo a calcular el nuevo estado
@param scenario La instancia del escenario
@return EL estado en la instancia t, con t0 la instancia inicial
"""
def _state_at(
    t0: float,
    state0: SpacecraftState,
    t: float,
    scenario: Scenario,
) -> SpacecraftState:

    if not math.isfinite(t0) or not math.isfinite(t):
        raise ValueError("Invalid time")

    if t < t0:
        raise ValueError("Target time precedes initial time")

    if t == t0:
        return state0

    return rk2_step(
        t0,
        state0,
        t - t0,
        scenario,
    )

"""
Calcula el primer momento de colisión dado un tiempo inicial t0, tiempo final t1 y sus correspondientes estados, tenienndo en cuenta una tolerancia de tolerance_s
"""
def _locate_body_collision(
    t0: float,
    state0: SpacecraftState,
    t1: float,
    state1: SpacecraftState,
    body: CollidableBody,
    body_start_m: Vec3,
    body_end_m: Vec3,
    scenario: Scenario,
    tolerance_s: float,
) -> tuple[float, SpacecraftState] | None:

    if is_collision(
        state1,
        body_end_m,
        body.radius_m,
    ):
        candidate_t = t1

    else:
        fraction = swept_collision_closest_fraction(
            state0.position_m,
            state1.position_m,
            body_start_m,
            body_end_m,
            body.radius_m,
        )

        if fraction is None:
            return None

        candidate_t = t0 + fraction * (t1 - t0)

        if candidate_t <= t0:
            return None

        candidate_state = _state_at(
            t0,
            state0,
            candidate_t,
            scenario,
        )

        candidate_body_position = body.pos(candidate_t)

        if not is_collision(
            candidate_state,
            candidate_body_position,
            body.radius_m,
        ):
            return None

    left_t = t0
    right_t = candidate_t

    for _ in range(MAX_BISECTION_ITERATIONS):

        if right_t - left_t <= tolerance_s:
            break

        mid_t = (left_t + right_t) / 2

        mid_state = _state_at(
            t0,
            state0,
            mid_t,
            scenario,
        )

        mid_body_position = body.pos(mid_t)

        if is_collision(
            mid_state,
            mid_body_position,
            body.radius_m,
        ):
            right_t = mid_t
        else:
            left_t = mid_t

    impact_state = _state_at(
        t0,
        state0,
        right_t,
        scenario,
    )

    return right_t, impact_state

def _locate_collision(
    t0: float,
    state0: SpacecraftState,
    t1: float,
    state1: SpacecraftState,
    start_positions_m: dict[str, Vec3],
    end_positions_m: dict[str, Vec3],
    scenario: Scenario,
    bodies: Sequence[CollidableBody],
    tolerance_s: float = COLLISION_TIME_TOLERANCE_S,
) -> tuple[
    float,
    SpacecraftState,
    dict[str, Vec3],
    CollidableBody,
] | None:
    """
    Localiza el primer impacto, considerando todos los cuerpos.

    Si hay varios impactos posibles dentro del intervalo, devuelve
    el que sucede primero.
    """

    if tolerance_s <= 0 or not math.isfinite(tolerance_s):
        raise ValueError("Invalid collision time tolerance")

    earliest_collision = None

    for body in bodies:

        if body.id not in start_positions_m:
            raise ValueError(f"Missing initial position for {body.id}")

        if body.id not in end_positions_m:
            raise ValueError(f"Missing final position for {body.id}")

        result = _locate_body_collision(
            t0,
            state0,
            t1,
            state1,
            body,
            start_positions_m[body.id],
            end_positions_m[body.id],
            scenario,
            tolerance_s,
        )

        if result is None:
            continue

        impact_time, impact_state = result

        if (
            earliest_collision is None
            or impact_time < earliest_collision[0]
        ):
            impact_positions = _body_positions_at(
                scenario,
                impact_time,
            )

            earliest_collision = (
                impact_time,
                impact_state,
                impact_positions,
                body,
            )

    return earliest_collision

"""
Ejecuta la simulación completa.

Devuelve:
    samples: muestras de la trayectoria.
    events: eventos detectados.
    status: estado final de la simulación.
"""
def integrate(
    config: SimulationConfig,
    scenario: Scenario,
) -> tuple[
    list[TrajectorySample],
    list[Event],
    SimulationStatus,
]:
    if (
        not math.isfinite(config.duration_s)
        or config.duration_s < 0
    ):
        raise ValueError("Invalid simulation duration")

    if (
        not math.isfinite(config.step_s)
        or config.step_s <= 0
    ):
        raise ValueError("Invalid integration step")

    bodies = scenario.get_bodies()

    body_ids = [body.id for body in bodies]

    if len(body_ids) != len(set(body_ids)):
        raise ValueError("Duplicate body identifiers")

    samples: list[TrajectorySample] = []
    events: list[Event] = []

    # Estado inicial.
    t_s = 0.0
    state = config.initial_state

    try:
        body_positions_m = _body_positions_at(
            scenario,
            t_s,
        )

        # Primera muestra obligatoria.
        samples.append(
            TrajectorySample(
                t_s=t_s,
                spacecraft=state,
                body_positions_m=body_positions_m,
            )
        )

        # Comprobar colisión inicial.
        collided_body = find_colliding_body(
            state,
            body_positions_m,
            bodies,
        )

        if collided_body is not None:
            events.append(
                Event(
                    type="collision",
                    t_s=t_s,
                    body_id=collided_body.id,
                    position_m=state.position_m,
                )
            )

            return (
                samples,
                events,
                SimulationStatus.COLLISION,
            )

    except (GravityError, ArithmeticError, ValueError):
        return (
            samples,
            events,
            SimulationStatus.NUMERICAL_ERROR,
        )

    # Bucle principal de integración.
    while t_s < config.duration_s:

        remaining_s = config.duration_s - t_s
        step_s = min(config.step_s, remaining_s)

        next_t_s = min(
            config.duration_s,
            t_s + step_s,
        )

        if next_t_s <= t_s:
            return (
                samples,
                events,
                SimulationStatus.NUMERICAL_ERROR,
            )

        actual_step_s = next_t_s - t_s

        try:
            # Calcular el siguiente estado mediante RK2.
            next_state = rk2_step(
                t_s,
                state,
                actual_step_s,
                scenario,
            )

            next_positions_m = _body_positions_at(
                scenario,
                next_t_s,
            )

            # Buscar colisiones dentro de todo el intervalo,
            # no solo en el instante final.
            collision = _locate_collision(
                t0=t_s,
                state0=state,
                t1=next_t_s,
                state1=next_state,
                start_positions_m=body_positions_m,
                end_positions_m=next_positions_m,
                scenario=scenario,
                bodies=bodies,
            )

        except (GravityError, ArithmeticError, ValueError):
            return (
                samples,
                events,
                SimulationStatus.NUMERICAL_ERROR,
            )

        if collision is not None:

            impact_time, impact_state, impact_positions, body = collision

            samples.append(
                TrajectorySample(
                    t_s=impact_time,
                    spacecraft=impact_state,
                    body_positions_m=impact_positions,
                )
            )

            events.append(
                Event(
                    type="collision",
                    t_s=impact_time,
                    body_id=body.id,
                    position_m=impact_state.position_m,
                )
            )

            return (
                samples,
                events,
                SimulationStatus.COLLISION,
            )

        # No hay impacto: aceptar el paso y guardar la muestra.
        samples.append(
            TrajectorySample(
                t_s=next_t_s,
                spacecraft=next_state,
                body_positions_m=next_positions_m,
            )
        )

        state = next_state
        t_s = next_t_s
        body_positions_m = next_positions_m

    return (
        samples,
        events,
        SimulationStatus.COMPLETED,
    )