"""Propagación adaptativa planar."""

from __future__ import annotations

import math
from scipy.integrate import solve_ivp

from app.physics.gravity import GravityError


def propagate_planar(
    scenario,
    position_m,
    velocity_m_s,
    t0: float,
    t1: float,
    *,
    events: bool = False,
    rtol: float = 1e-10,
    atol: float = 1e-6,
    dense_output: bool = True,
):
    """DOP853 planar sin asignaciones por subpaso.

    Mantiene la misma dinámica newtoniana de ``gravity.py`` y la misma firma
    por defecto, pero valida constantes una sola vez y usa ``pos_xy_fast(t)``
    cuando el escenario lo expone.
    """
    bodies = scenario.get_bodies()
    fast_bodies = []
    for body in bodies:
        mu = float(body.mu_m3_s2)
        radius = float(body.radius_m)
        if not math.isfinite(mu) or mu <= 0.0 or not math.isfinite(radius) or radius <= 0.0:
            raise GravityError(f"Invalid gravitational body: {body.id}")
        contact_radius = radius - (1.0 if body.id == "earth" else 0.0)
        pos_fast = getattr(body, "pos_xy_fast", None)
        fast_bodies.append((body, body.id, mu, contact_radius, pos_fast))

    sqrt = math.sqrt
    isfinite = math.isfinite

    # Camino rápido especializado para el caso estándar Tierra–Luna (2 cuerpos)
    if len(fast_bodies) == 2 and fast_bodies[0][4] is not None and fast_bodies[1][4] is not None:
        _, id0, mu0, _, pos0 = fast_bodies[0]
        _, id1, mu1, _, pos1 = fast_bodies[1]

        def derivative(t: float, state):
            sx = float(state[0])
            sy = float(state[1])

            bx0, by0 = pos0(t)
            dx0 = sx - bx0
            dy0 = sy - by0
            r2_0 = dx0 * dx0 + dy0 * dy0
            if not isfinite(r2_0) or r2_0 <= 0.0:
                raise GravityError(f"Invalid distance to {id0}")
            f0 = -mu0 / (r2_0 * sqrt(r2_0))

            bx1, by1 = pos1(t)
            dx1 = sx - bx1
            dy1 = sy - by1
            r2_1 = dx1 * dx1 + dy1 * dy1
            if not isfinite(r2_1) or r2_1 <= 0.0:
                raise GravityError(f"Invalid distance to {id1}")
            f1 = -mu1 / (r2_1 * sqrt(r2_1))

            return (
                float(state[2]),
                float(state[3]),
                f0 * dx0 + f1 * dx1,
                f0 * dy0 + f1 * dy1,
            )
    else:
        def derivative(t: float, state):
            sx = float(state[0])
            sy = float(state[1])
            ax = 0.0
            ay = 0.0
            for body, body_id, mu, _, pos_fast in fast_bodies:
                if pos_fast is not None:
                    bx, by = pos_fast(t)
                else:
                    bx, by, _ = body.pos(t)
                dx = sx - bx
                dy = sy - by
                r2 = dx * dx + dy * dy
                if not isfinite(r2) or r2 <= 0.0:
                    raise GravityError(f"Invalid distance to {body_id}")
                factor = -mu / (r2 * sqrt(r2))
                ax += factor * dx
                ay += factor * dy
            return float(state[2]), float(state[3]), ax, ay

    event_functions = []
    if events:
        hypot = math.hypot
        for body, _, _, contact_radius, pos_fast in fast_bodies:
            def contact(t: float, state, body=body, radius=contact_radius, pos_fast=pos_fast):
                if pos_fast is not None:
                    bx, by = pos_fast(t)
                else:
                    bx, by, _ = body.pos(t)
                return hypot(float(state[0]) - bx, float(state[1]) - by) - radius

            contact.direction = -1
            contact.terminal = False
            event_functions.append(contact)

    solution = solve_ivp(
        derivative,
        (t0, t1),
        (float(position_m[0]), float(position_m[1]), float(velocity_m_s[0]), float(velocity_m_s[1])),
        method="DOP853",
        rtol=rtol,
        atol=atol,
        dense_output=dense_output,
        events=event_functions or None,
        max_step=min(3600.0, (t1 - t0) / 100.0),
    )
    if not solution.success:
        raise RuntimeError(f"Falló la propagación: {solution.message}")
    return solution