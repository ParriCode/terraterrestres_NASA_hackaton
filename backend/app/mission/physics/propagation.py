"""Propagación adaptativa planar con la gravedad compartida del proyecto."""

import math

import numpy as np
from scipy.integrate import solve_ivp


def propagate_planar(scenario, position_m, velocity_m_s, t0, t1, *, events=False):
    """DOP853 con salida densa. Durante shooting se desactivan los eventos.

    Los eventos registran cruces entrantes; la holgura terrestre de 1 m permite
    partir de la superficie sin identificar la salida como una colisión.
    """
    bodies = scenario.get_bodies()
    # Propagación 2D en el plano del baricentro: evitar construir diccionarios,
    # tuplas y validar invariantes físicas dentro de cada evaluación DOP853.
    motions = [(body.id, body.mu_m3_s2, getattr(body, "_motion", None), body) for body in bodies]

    def derivative(t, state):
        x, y = state[:2]
        ax = ay = 0.0
        for body_id, mu, motion, body in motions:
            bx, by = motion(t)[:2] if callable(motion) else body.pos(t)[:2]
            dx, dy = bx - x, by - y
            dist_sq = dx * dx + dy * dy
            if dist_sq <= 0.0:
                raise ValueError(f"Posición singular en la gravedad de {body_id}")
            inv_dist3 = mu / (dist_sq * math.sqrt(dist_sq))
            ax += dx * inv_dist3
            ay += dy * inv_dist3
            if body_id == "sun":
                b_sq = bx * bx + by * by
                if b_sq > 0:
                    factor = mu / (b_sq * math.sqrt(b_sq))
                    ax -= bx * factor
                    ay -= by * factor
        return state[2], state[3], ax, ay

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
        method="DOP853", rtol=2e-9, atol=(0.01, 0.01, 1e-5, 1e-5), dense_output=True,
        events=event_functions or None, max_step=min(5400.0, (t1 - t0) / 80),
    )
    if not solution.success:
        raise RuntimeError(f"Falló la propagación: {solution.message}")
    return solution
