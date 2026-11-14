"""Ecuaciones de movimiento."""

from app.data.scenarios import Scenario
from app.models.domain import CelestialBody, SpacecraftState, Vec3
from app.physics.gravity import gravitational_acceleration

"""
!Recibe tiempo al próximo cambio, estado actual de la nave, posición e instancia de los cuerpos, calcula el próximo estado derivado del actual pasado un tiempo t_s produciendo un movimiento lineal
@param t_s Tiempo hasta el próximo cambio
@param state Estado actual de la nave espacia
@param body_positions_m Hash table para las posiciones de los cuerpos
@param bodies Lista de cuerpos
@return Tupla de la velocidad actual de la nave y la aceleración que siente
"""
# TODO dado posición t_s saber posición de un cuerpo
def state_derivative(
    t_s: float,
    state: SpacecraftState,
    scenario: Scenario,
    bodies: list[CelestialBody],
) -> tuple[Vec3, Vec3]:
    body_positions_m: dict[str, Vec3] = {}

    for body in bodies:
        body_positions_m[body.id] = scenario.get_body_pos(body, t_s)

    acceleration = gravitational_acceleration(
        state.position_m,
        body_positions_m,
        bodies,
    )
    return (
        state.velocity_m_s,
        acceleration,
    )
