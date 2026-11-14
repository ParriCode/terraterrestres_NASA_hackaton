"""Integrador del punto medio RK2."""

import math
from app.data.scenarios import Scenario
from app.models.domain import CelestialBody, SimulationConfig, SimulationStatus, SpacecraftState, TrajectorySample, Vec3
from app.models.domain import Event
from app.physics.dynamics import state_derivative

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
!Recibe configuración y proveedor de cuerpos
@return muestras
"""
def integrate(
    config: SimulationConfig,
    scenario,
) -> tuple[list[TrajectorySample], list[Event], SimulationStatus]:
    pass
