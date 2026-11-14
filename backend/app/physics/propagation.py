"""Propagación adaptativa planar con la gravedad compartida del proyecto."""

import numpy as np
from scipy.integrate import solve_ivp

from app.physics.gravity import gravitational_acceleration


def propagate_planar(scenario, position_m, velocity_m_s, t0, t1, *, events=False, budget_check=None):
    """DOP853 con salida densa. Durante shooting se desactivan los eventos.

    Los eventos registran cruces entrantes; la holgura terrestre de 1 m permite
    partir de la superficie sin identificar la salida como una colisión.
    """
    bodies = scenario.get_bodies()

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
    if events:
        for body in bodies:
            def contact(t, state, body=body):
                radius = body.radius_m - (1.0 if body.id == "earth" else 0.0)
                return np.linalg.norm(state[:2] - np.asarray(body.pos(t))[:2]) - radius
            contact.direction = -1
            contact.terminal = False
            event_functions.append(contact)
    solution = solve_ivp(
        derivative, (t0, t1), (*position_m[:2], *velocity_m_s[:2]),
        method="DOP853", rtol=1e-10, atol=1e-6, dense_output=True,
        events=event_functions or None, max_step=min(3600.0, (t1 - t0) / 100),
    )
    if not solution.success:
        raise RuntimeError(f"Falló la propagación: {solution.message}")
    return solution
