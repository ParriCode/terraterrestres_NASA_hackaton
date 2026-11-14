"""Ecuaciones de movimiento."""

from app.data.scenarios import Scenario
from app.models.domain import SpacecraftState, Vec3
from app.physics.gravity import gravitational_acceleration

def state_derivative(
    t_s: float,
    state: SpacecraftState,
    scenario: Scenario,
) -> tuple[Vec3, Vec3]:
    """Devuelve (velocidad, aceleración) usando los cuerpos del escenario en t_s."""
    bodies = scenario.get_bodies()
    body_positions_m = {body.id: body.pos(t_s) for body in bodies}
    acceleration = gravitational_acceleration(
        state.position_m,
        body_positions_m,
        bodies,
    )
    return (
        state.velocity_m_s,
        acceleration,
    )
