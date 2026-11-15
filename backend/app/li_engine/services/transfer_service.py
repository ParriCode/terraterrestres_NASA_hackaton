"""F del documento: Lambert, shooting y trayectoria planar con datos Horizons."""
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from app.li_engine.data.scenarios import PlanarScenario
from app.li_engine.models.domain import SpacecraftState, Vec3, validate_positive, validate_vec3
from app.li_engine.physics.lambert import LambertError, solve_lambert
from app.li_engine.physics.propagation import propagate_planar
from app.li_engine.physics.shooting import solve_shooting


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
    launch_delta_v_m_s: float
    arrival_v_infinity_m_s: float
    arrival_delta_v_m_s: float
    total_delta_v_m_s: float
    parking_alt_m: float = 0.0
    _solution: object = field(repr=False, default=None)

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
        return {
            "kinetic_j": float(kinetic),
            "potential_j": float(potential),
            "mechanical_j": float(kinetic + potential),
        }


def orbit_point(body, other, time_s: float, angle_deg: float, altitude_m: float = 0.0) -> Vec3:
    """Devuelve un punto (x, y, 0) a radio body.radius_m + altitude_m."""
    center = np.asarray(body.pos(time_s))
    direction = np.asarray(other.pos(time_s)) - center
    theta = np.arctan2(direction[1], direction[0]) + np.deg2rad(angle_deg)
    radius = body.radius_m + altitude_m
    point = center + radius * np.array((np.cos(theta), np.sin(theta), 0.0))
    return (float(point[0]), float(point[1]), 0.0)


def prograde_circular_velocity(mu_m3_s2: float, rel_pos_m: np.ndarray) -> np.ndarray:
    """Velocidad circular tangencial prograde (sentido antihorario en XY)."""
    r_mag = float(np.linalg.norm(rel_pos_m))
    u_r = rel_pos_m / r_mag
    u_t = np.array((-u_r[1], u_r[0], 0.0))
    v_circ = float(np.sqrt(mu_m3_s2 / r_mag))
    return v_circ * u_t


def _earth_positions_xy(earth, times: np.ndarray) -> np.ndarray:
    """Evalúa la posición XY de la Tierra vectorizada sobre todo el array de tiempos."""
    motion = getattr(earth, "_motion", None)
    if callable(motion):
        return np.asarray(motion(times))[:, :2]
    return np.array([earth.pos(float(t))[:2] for t in times])


def F(
    x0: Vec3,
    x1: Vec3,
    t0: float,
    t1: float,
    objetivo="energia",
    *,
    scenario: PlanarScenario,
    mass_kg=1.0,
    arrival_tolerance_m=1000.0,
    parking_alt_m: float = 0.0,
    prograde_hint: bool | None = None,
    warm_start_velocity: Vec3 | None = None,
) -> TransferResult:
    """Busca la mejor candidata válida entre semillas Lambert o arranque en caliente."""
    validate_vec3(x0, "x0")
    validate_vec3(x1, "x1")
    validate_positive(mass_kg, "mass_kg")
    validate_positive(arrival_tolerance_m, "arrival_tolerance_m")
    if not np.isfinite(parking_alt_m) or parking_alt_m < 0:
        raise ValueError("parking_alt_m debe ser finito y no negativo.")
    if not 0 <= t0 < t1 <= scenario.duration_s:
        raise ValueError("Se requiere 0 <= t0 < t1 <= duración del escenario.")
    if x0[2] != 0 or x1[2] != 0:
        raise ValueError("F trabaja en 2D: z debe ser cero.")
    if objetivo not in ("energia", "distancia", "delta_v"):
        raise ValueError("objetivo debe ser energia, distancia o delta_v.")

    earth, moon = scenario.bodies["earth"], scenario.bodies["moon"]
    start, target = np.asarray(x0), np.asarray(x1)
    if abs(np.linalg.norm(start - earth.pos(t0)) - (earth.radius_m + parking_alt_m)) > 1.0:
        raise ValueError("El extremo inicial debe estar en la órbita de aparcamiento terrestre.")
    if abs(np.linalg.norm(target - moon.pos(t1)) - moon.radius_m) > 1.0:
        raise ValueError("El extremo objetivo debe estar en la superficie lunar.")

    earth_velocity = np.asarray(earth.speed(t0))
    rel_start = start - np.asarray(earth.pos(t0))
    v_circ_vec = prograde_circular_velocity(earth.mu_m3_s2, rel_start)
    v_esc_moon_sq = 2.0 * moon.mu_m3_s2 / moon.radius_m
    body_keys = list(scenario.bodies)
    earth_index = body_keys.index("earth")
    moon_index = body_keys.index("moon")
    valid: list[TransferResult] = []
    reasons: list[str] = []

    def residual(velocity):
        solution = propagate_planar(scenario, x0, velocity, t0, t1)
        final = solution.y[:2, -1] - target[:2]
        return float(final[0]), float(final[1]), 0.0

    def _validate_guess(guess: Vec3, max_evals: int) -> None:
        shot = solve_shooting(
            guess,
            residual,
            planar=True,
            arrival_tolerance_m=arrival_tolerance_m,
            max_evaluations=max_evals,
        )
        if not shot.converged:
            reasons.append(f"Error de llegada: {shot.residual_norm_m:.1f} m")
            return
        velocity = np.asarray(shot.initial_velocity_m_s)
        if any(np.linalg.norm(velocity - r.initial_velocity_m_s) < 1.0 for r in valid):
            return
        solution = propagate_planar(scenario, x0, velocity, t0, t1, events=True)
        if len(solution.t_events[earth_index]):
            reasons.append("La trayectoria vuelve a tocar la Tierra")
            return
        if any(t < t1 - 600.0 for t in solution.t_events[moon_index]):
            reasons.append("Primer contacto lunar antes de tiempo")
            return
        final_position = np.array((*solution.y[:2, -1], 0.0))
        final_velocity = np.array((*solution.y[2:, -1], 0.0))
        error = float(np.linalg.norm(final_position - target))
        if error > arrival_tolerance_m:
            reasons.append("Error de llegada tras validar")
            return
        if np.dot(final_velocity - moon.speed(t1), final_position - moon.pos(t1)) >= 0:
            reasons.append("La nave no llega desde fuera de la Luna")
            return

        times = np.linspace(t0, t1, 1200)
        spacecraft_xy = solution.sol(times)[:2].T
        relative = spacecraft_xy - _earth_positions_xy(earth, times)
        if float(np.min(np.linalg.norm(relative, axis=1))) < earth.radius_m - 10.0:
            reasons.append("La trayectoria penetra en la Tierra")
            return

        length = float(np.linalg.norm(np.diff(spacecraft_xy, axis=0), axis=1).sum())
        rel_dep_vel = velocity - earth_velocity
        launch_speed = float(np.linalg.norm(rel_dep_vel))
        launch_delta_v = float(np.linalg.norm(rel_dep_vel - v_circ_vec))
        arrival_delta_v = float(np.linalg.norm(final_velocity - moon.speed(t1)))
        arrival_v_inf = float(np.sqrt(max(0.0, arrival_delta_v**2 - v_esc_moon_sq)))
        total_delta_v = float(launch_delta_v + arrival_delta_v)
        valid.append(
            TransferResult(
                scenario,
                t0,
                t1,
                shot.initial_velocity_m_s,
                launch_speed,
                0.5 * mass_kg * launch_speed**2,
                length,
                error,
                mass_kg,
                objetivo,
                launch_delta_v,
                arrival_v_inf,
                arrival_delta_v,
                total_delta_v,
                float(parking_alt_m),
                solution,
            )
        )

    if warm_start_velocity is not None:
        try:
            _validate_guess(warm_start_velocity, max_evals=35)
        except (RuntimeError, ArithmeticError, ValueError) as error:
            reasons.append(str(error))

    if not valid:
        prograde_seq = (prograde_hint,) if prograde_hint is not None else (True, False)
        factor_groups = ((1.0,),) if prograde_hint is not None else ((1.0,), (0.98, 1.02))
        rel_r1 = tuple(start - earth.pos(t0))
        rel_r2 = tuple(target - earth.pos(t1))
        for factors in factor_groups:
            if valid:
                break
            for prograde in prograde_seq:
                for factor in factors:
                    try:
                        seed = solve_lambert(
                            rel_r1,
                            rel_r2,
                            (t1 - t0) * factor,
                            earth.mu_m3_s2,
                            prograde=prograde,
                        )
                        guess = tuple(np.asarray(seed.departure_velocity_m_s) + earth_velocity)
                        _validate_guess(guess, max_evals=55)
                    except (LambertError, RuntimeError, ArithmeticError, ValueError) as error:
                        reasons.append(str(error))

    if not valid:
        raise TransferNotFoundError(
            "No se encontró transferencia válida: " + "; ".join(sorted(set(reasons)))
        )
    if objetivo == "energia":
        key = lambda r: r.launch_energy_j
    elif objetivo == "distancia":
        key = lambda r: r.path_length_m
    else:
        key = lambda r: r.total_delta_v_m_s
    return min(valid, key=key)


def design_transfer(
    date: datetime,
    duration_s: float,
    *,
    launch_angle_deg=90.0,
    arrival_angle_deg=0.0,
    objective="energia",
    mass_kg=1.0,
    spacing_s=3600.0,
    parking_alt_m: float = 0.0,
) -> TransferResult:
    """Carga NASA y llama a F. Alfa: desde Tierra→Luna; beta: Luna→Tierra."""
    if not np.isfinite(launch_angle_deg) or not np.isfinite(arrival_angle_deg):
        raise ValueError("Los ángulos deben ser finitos.")
    if not np.isfinite(parking_alt_m) or parking_alt_m < 0:
        raise ValueError("parking_alt_m debe ser finito y no negativo.")
    scenario = PlanarScenario(date, duration_s, spacing_s=spacing_s)
    earth, moon = scenario.bodies["earth"], scenario.bodies["moon"]
    return F(
        orbit_point(earth, moon, 0.0, launch_angle_deg, parking_alt_m),
        orbit_point(moon, earth, duration_s, arrival_angle_deg, 0.0),
        0.0,
        duration_s,
        objective,
        scenario=scenario,
        mass_kg=mass_kg,
        parking_alt_m=parking_alt_m,
    )