"""Propagación adaptativa planar."""

from __future__ import annotations

import math
from scipy.integrate import solve_ivp

from app.physics.gravity import GravityError


def propagate_planar(scenario, position_m, velocity_m_s, t0, t1, *, events=False, budget_check=None):
    """DOP853 con salida densa; detiene el vuelo ante el primer impacto.

    Se comprueban los impactos también durante *shooting*: permitir que una
    candidata provisional atraviese un planeta provoca integraciones muy
    lentas cerca de la singularidad gravitatoria. La holgura de 1 m para la
    Tierra permite iniciar el vuelo exactamente en su superficie.

    ``events`` se conserva por compatibilidad con los llamadores existentes;
    la protección ante colisiones está activa en ambos casos.
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

    calls = 0

    def derivative(t, state):
        nonlocal calls
        calls += 1
        if budget_check is not None and calls % 32 == 1:
            budget_check()
        positions = {body.id: body.pos(t) for body in bodies}
        a = gravitational_acceleration(
            (float(state[0]), float(state[1]), 0.0), positions, bodies,
            check_surface=False,
        )
        return state[2], state[3], a[0], a[1]

    event_functions = []
    # Detener cada propagación al primer impacto (también durante shooting).
    # Continuar dentro de un cuerpo provoca pasos infinitesimales cerca del centro.
    for body in bodies:
        def contact(t, state, body=body):
            radius = body.radius_m - (1.0 if body.id == "earth" else 0.0)
            return np.linalg.norm(state[:2] - np.asarray(body.pos(t))[:2]) - radius
        contact.direction = -1
        contact.terminal = True
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