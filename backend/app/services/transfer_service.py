"""F del documento: Lambert, shooting y trayectoria planar con datos Horizons.

Tiempos en segundos desde scenario.date. Coordenadas del plano orbital inicial
del escenario, origen baricéntrico y z=0. Se ignoran rotación y otras gravedades.
"""
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from app.data.scenarios import PlanarScenario
from app.models.domain import SpacecraftState, Vec3, validate_positive, validate_vec3
from app.physics.lambert import LambertError, solve_lambert
from app.physics.propagation import propagate_planar
from app.physics.shooting import solve_shooting


class TransferNotFoundError(RuntimeError):
    """Ninguna semilla produjo una transferencia válida."""


@dataclass(frozen=True)
class TransferResult:
    scenario: PlanarScenario
    t0_s: float
    t1_s: float
    initial_velocity_m_s: Vec3
    launch_speed_m_s: float
    launch_energy_j: float
    path_length_m: float
    arrival_error_m: float
    mass_kg: float
    objective: str
    _solution: object = field(repr=False)

    def state(self, time_s: float) -> SpacecraftState:
        """Estado interpolado sin reintegrar, dentro del intervalo del vuelo."""
        if not np.isfinite(time_s) or not self.t0_s <= time_s <= self.t1_s:
            raise ValueError("Tiempo fuera del intervalo de la transferencia.")
        x, y, vx, vy = self._solution.sol(time_s)
        return SpacecraftState((float(x), float(y), 0.0), (float(vx), float(vy), 0.0))

    def pos(self, time_s: float) -> Vec3:
        return self.state(time_s).position_m

    def speed(self, time_s: float) -> Vec3:
        """Vector velocidad en m/s, en los ejes fijos del escenario."""
        return self.state(time_s).velocity_m_s

    def C(self, time_s: float) -> tuple[Vec3, Vec3]:
        state = self.state(time_s)
        return state.position_m, state.velocity_m_s

    def energy(self, time_s: float) -> dict[str, float]:
        """Energía baricéntrica; no es constante con potenciales móviles."""
        state = self.state(time_s)
        r = np.asarray(state.position_m)
        kinetic = 0.5 * self.mass_kg * np.dot(state.velocity_m_s, state.velocity_m_s)
        potential = -self.mass_kg * sum(
            body.mu_m3_s2 / np.linalg.norm(r - body.pos(time_s))
            for body in self.scenario.get_bodies()
        )
        return {"kinetic_j": float(kinetic), "potential_j": float(potential),
                "mechanical_j": float(kinetic + potential)}


def F(x0: Vec3, x1: Vec3, t0: float, t1: float, objetivo="energia", *,
      scenario: PlanarScenario, mass_kg=1.0, arrival_tolerance_m=1000.0) -> TransferResult:
    """Busca la mejor candidata válida entre semillas Lambert pro/retrógradas.

    Replica F del documento, sin garantía de óptimo global. La energía de
    lanzamiento se mide respecto al centro terrestre. La longitud se mide
    respecto a la Tierra en ejes fijos. Los extremos están en las superficies.
    """
    validate_vec3(x0, "x0")
    validate_vec3(x1, "x1")
    validate_positive(mass_kg, "mass_kg")
    validate_positive(arrival_tolerance_m, "arrival_tolerance_m")
    if not 0 <= t0 < t1 <= scenario.duration_s:
        raise ValueError("Se requiere 0 <= t0 < t1 <= duración del escenario.")
    if x0[2] != 0 or x1[2] != 0:
        raise ValueError("F trabaja en 2D: z debe ser cero.")
    if objetivo not in ("energia", "distancia"):
        raise ValueError("objetivo debe ser energia o distancia.")
    earth, moon = scenario.bodies["earth"], scenario.bodies["moon"]
    start, target = np.asarray(x0), np.asarray(x1)
    for point, body, t in ((start, earth, t0), (target, moon, t1)):
        if abs(np.linalg.norm(point - body.pos(t)) - body.radius_m) > 1.0:
            raise ValueError("Los extremos deben estar en las superficies terrestre y lunar.")
    earth_velocity = np.asarray(earth.speed(t0))
    normal = start - earth.pos(t0)
    normal /= np.linalg.norm(normal)
    valid, reasons = [], []

    def residual(velocity):
        solution = propagate_planar(scenario, x0, velocity, t0, t1)
        final = solution.y[:2, -1] - target[:2]
        return float(final[0]), float(final[1]), 0.0

    for factors in ((1.0,), (0.98, 1.02)):
        if valid:
            break
        for prograde in (True, False):
            for factor in factors:
                try:
                    seed = solve_lambert(
                        tuple(start - earth.pos(t0)), tuple(target - earth.pos(t1)),
                        (t1 - t0) * factor, earth.mu_m3_s2, prograde=prograde,
                    )
                    guess = tuple(np.asarray(seed.departure_velocity_m_s) + earth_velocity)
                    shot = solve_shooting(guess, residual, planar=True,
                                          arrival_tolerance_m=arrival_tolerance_m,
                                          max_evaluations=200)
                    if not shot.converged:
                        reasons.append(f"Error de llegada: {shot.residual_norm_m:.1f} m")
                        continue
                    velocity = np.asarray(shot.initial_velocity_m_s)
                    if np.dot(velocity - earth_velocity, normal) <= 0:
                        reasons.append("La salida entra en la Tierra")
                        continue
                    if any(np.linalg.norm(velocity - r.initial_velocity_m_s) < 1 for r in valid):
                        continue
                    solution = propagate_planar(scenario, x0, velocity, t0, t1, events=True)
                    earth_index = list(scenario.bodies).index("earth")
                    moon_index = list(scenario.bodies).index("moon")
                    if len(solution.t_events[earth_index]):
                        reasons.append("La trayectoria vuelve a tocar la Tierra")
                        continue
                    if any(t < t1 - 60.0 for t in solution.t_events[moon_index]):
                        reasons.append("Primer contacto lunar antes de tiempo")
                        continue
                    final_position = np.array((*solution.y[:2, -1], 0.0))
                    final_velocity = np.array((*solution.y[2:, -1], 0.0))
                    error = float(np.linalg.norm(final_position - target))
                    if error > arrival_tolerance_m:
                        reasons.append("Error de llegada tras validar")
                        continue
                    if np.dot(final_velocity - moon.speed(t1), final_position - moon.pos(t1)) >= 0:
                        reasons.append("La nave no llega desde fuera de la Luna")
                        continue
                    times = np.linspace(t0, t1, 4000)
                    relative = solution.sol(times)[:2].T - np.array([earth.pos(t)[:2] for t in times])
                    length = float(np.linalg.norm(np.diff(relative, axis=0), axis=1).sum())
                    launch_speed = float(np.linalg.norm(velocity - earth_velocity))
                    valid.append(TransferResult(
                        scenario, t0, t1, shot.initial_velocity_m_s, launch_speed,
                        0.5 * mass_kg * launch_speed**2, length, error,
                        mass_kg, objetivo, solution,
                    ))
                except (LambertError, RuntimeError, ArithmeticError, ValueError) as error:
                    reasons.append(str(error))
    if not valid:
        raise TransferNotFoundError("No se encontró transferencia válida: " + "; ".join(sorted(set(reasons))))
    return min(valid, key=lambda r: r.launch_energy_j if objetivo == "energia" else r.path_length_m)


def design_transfer(date: datetime, duration_s: float, *, launch_angle_deg=90.0,
                    arrival_angle_deg=0.0, objective="energia", mass_kg=1.0,
                    spacing_s=3600.0) -> TransferResult:
    """Carga NASA y llama a F. Alfa: desde Tierra→Luna; beta: Luna→Tierra.

    Los ángulos son geométricos del modelo planar, no latitud/longitud.
    """
    if not np.isfinite(launch_angle_deg) or not np.isfinite(arrival_angle_deg):
        raise ValueError("Los ángulos deben ser finitos.")
    scenario = PlanarScenario(date, duration_s, spacing_s=spacing_s)
    earth, moon = scenario.bodies["earth"], scenario.bodies["moon"]

    def surface(body, other, time, angle):
        center = np.asarray(body.pos(time))
        direction = np.asarray(other.pos(time)) - center
        theta = np.arctan2(direction[1], direction[0]) + np.deg2rad(angle)
        return tuple(center + body.radius_m * np.array((np.cos(theta), np.sin(theta), 0.0)))

    return F(surface(earth, moon, 0, launch_angle_deg),
             surface(moon, earth, duration_s, arrival_angle_deg),
             0.0, duration_s, objective, scenario=scenario, mass_kg=mass_kg)
