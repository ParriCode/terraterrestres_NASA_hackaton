"""Ecuaciones de movimiento para el escenario Tierra-Luna (SI)."""

from app.data.scenarios import Scenario
from app.models.domain import SpacecraftState, Vec3
from app.physics.gravity import gravitational_acceleration


def get_body_position_m(scenario: Scenario, body, t_s: float) -> Vec3:
    """Resuelve la posición del cuerpo mediante un único proveedor coherente.

    Contrato v1 preferido: Scenario.get_body_pos(body, t_s).
    Compatibilidad con la variante incluida en physics.zip: body.pos(t_s).
    Scenario debe resolver posiciones desde efemérides en memoria o caché;
    la física no implementa ni garantiza esa política de acceso.
    """
    provider = getattr(scenario, "get_body_pos", None)
    if callable(provider):
        return provider(body, t_s)
    legacy_provider = getattr(body, "pos", None)
    if callable(legacy_provider):
        return legacy_provider(t_s)
    raise TypeError(
        f"No position provider for body {body.id}: expected "
        "scenario.get_body_pos(body, t_s) or body.pos(t_s)"
    )


def state_derivative(
    t_s: float,
    state: SpacecraftState,
    scenario: Scenario,
) -> tuple[Vec3, Vec3]:
    """Devuelve (dr/dt, dv/dt) = (velocidad, aceleración gravitatoria)."""
    bodies = scenario.get_bodies()
    body_positions_m = {
        body.id: get_body_position_m(scenario, body, t_s) for body in bodies
    }
    acceleration = gravitational_acceleration(
        state.position_m, body_positions_m, bodies
    )
    return state.velocity_m_s, acceleration