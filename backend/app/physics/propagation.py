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
    budget_check=None,
    rtol: float = 1e-10,
    atol: float = 1e-6,
    dense_output: bool = True,
    stop_at_earth_radius_m: float | None = None,
):
    bodies = scenario.get_bodies()
    fast_bodies = []
    for body in bodies:
        mu = float(body.mu_m3_s2)
        radius = float(body.radius_m)
        if not math.isfinite(mu) or mu <= 0.0 or not math.isfinite(radius) or radius <= 0.0:
            raise GravityError(f"Invalid gravitational body: {body.id}")
        if events:
            contact_radius = radius - (1.0 if body.id == "earth" else 0.0)
        else:
            contact_radius = (radius - 1.0) if body.id == "earth" else (0.5 * radius)
        motion = getattr(body, "_motion", None)
        pos_fast = motion.pos_xy if motion is not None else getattr(body, "pos_xy_fast", None)
        fast_bodies.append((body, body.id, mu, contact_radius, pos_fast))

    sqrt = math.sqrt
    isfinite = math.isfinite
    hypot = math.hypot
    calls = 0

    def derivative(t: float, state):
        nonlocal calls
        calls += 1
        if budget_check is not None and (calls & 31) == 1:
            budget_check()
        sx, sy = float(state[0]), float(state[1])
        ax = ay = 0.0
        for body, body_id, mu, _, pos_fast in fast_bodies:
            bx, by = pos_fast(t) if pos_fast is not None else body.pos(t)[:2]
            dx, dy = sx - bx, sy - by
            r2 = dx * dx + dy * dy
            if not isfinite(r2) or r2 <= 0.0:
                raise GravityError(f"Invalid distance to {body_id}")
            factor = -mu / (r2 * sqrt(r2))
            ax += factor * dx
            ay += factor * dy
        return float(state[2]), float(state[3]), ax, ay

    if stop_at_earth_radius_m is not None:
        earth = next((body for body in bodies if body.id == "earth"), None)
        if earth is None or not math.isfinite(stop_at_earth_radius_m) or stop_at_earth_radius_m <= earth.radius_m:
            raise ValueError("La interfaz terrestre debe ser mayor que el radio físico de la Tierra.")
        ex, ey = earth.pos(t0)[:2]
        if math.hypot(float(position_m[0]) - ex, float(position_m[1]) - ey) <= stop_at_earth_radius_m:
            raise ValueError("El retorno debe comenzar fuera de la esfera terrestre objetivo.")

    event_functions = []
    for body, _, _, contact_radius, pos_fast in fast_bodies:
        def contact(t: float, state, body=body, radius=contact_radius, pos_fast=pos_fast):
            bx, by = pos_fast(t) if pos_fast is not None else body.pos(t)[:2]
            return hypot(float(state[0]) - bx, float(state[1]) - by) - radius

        contact.direction = -1
        contact.terminal = not events
        event_functions.append(contact)

    if stop_at_earth_radius_m is not None:
        earth = next(body for body in bodies if body.id == "earth")
        motion = getattr(earth, "_motion", None)
        earth_pos = motion.pos_xy if motion is not None else getattr(earth, "pos_xy_fast", None)

        def return_crossing(t: float, state):
            ex, ey = earth_pos(t) if earth_pos is not None else earth.pos(t)[:2]
            return math.hypot(float(state[0]) - ex, float(state[1]) - ey) - stop_at_earth_radius_m

        return_crossing.direction = -1
        return_crossing.terminal = True
        event_functions.append(return_crossing)  # Último evento, distinguible de impactos

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