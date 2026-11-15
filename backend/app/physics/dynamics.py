"""Ecuaciones de movimiento para el escenario cislunar de N cuerpos (SI)."""

from __future__ import annotations

import numpy as np

from app.data.scenarios import Scenario
from app.models.domain import SpacecraftState, Vec3
from app.physics.gravity import gravitational_acceleration


def get_body_position_m(scenario: Scenario, body, t_s: float) -> Vec3:
    """Resuelve la posición del cuerpo mediante el contrato de escenario."""
    if hasattr(scenario, "get_body_pos"):
        return scenario.get_body_pos(body, t_s)
    return body.pos(t_s)

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
    ax, ay, az = gravitational_acceleration(
        state.position_m, body_positions_m, bodies
    )
    if "sun" in body_positions_m:
        sun = next((b for b in bodies if b.id == "sun"), None)
        if sun is not None:
            bx, by, bz = body_positions_m["sun"]
            norm_b_sq = bx * bx + by * by + bz * bz
            if norm_b_sq > 0.0:
                indirect = sun.mu_m3_s2 / (norm_b_sq * (norm_b_sq ** 0.5))
                ax -= bx * indirect
                ay -= by * indirect
                az -= bz * indirect
    return state.velocity_m_s, (ax, ay, az)


def state_derivative_array(
    t_s: float,
    y: np.ndarray,
    bodies: tuple,
) -> np.ndarray:
    """Versión vectorizada para scipy.integrate.solve_ivp (y = [x, y, z, vx, vy, vz])."""
    rx, ry, rz = float(y[0]), float(y[1]), float(y[2])
    ax = ay = az = 0.0
    for body in bodies:
        bx, by, bz = body.pos(t_s)
        dx = bx - rx
        dy = by - ry
        dz = bz - rz
        dist_sq = dx * dx + dy * dy + dz * dz
        if dist_sq == 0.0:
            continue
        inv_dist3 = body.mu_m3_s2 / (dist_sq * np.sqrt(dist_sq))
        ax += dx * inv_dist3
        ay += dy * inv_dist3
        az += dz * inv_dist3
        if body.id == "sun":
            # Horizons CENTER=500@3: el baricentro Tierra-Luna no es inercial.
            # Se resta la aceleración solar del origen del marco (término indirecto).
            norm_b_sq = bx * bx + by * by + bz * bz
            if norm_b_sq > 0.0:
                indirect = body.mu_m3_s2 / (norm_b_sq * np.sqrt(norm_b_sq))
                ax -= bx * indirect
                ay -= by * indirect
                az -= bz * indirect
    return np.array((y[3], y[4], y[5], ax, ay, az), dtype=np.float64)