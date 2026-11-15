"""Resolución tridimensional del problema de Lambert."""

from dataclasses import dataclass
import math

from app.mission.models.domain import Vec3, validate_positive, validate_vec3


class LambertError(ValueError):
    """El problema de Lambert no tiene solución con los datos indicados."""


@dataclass(frozen=True)
class LambertSolution:
    departure_velocity_m_s: Vec3
    arrival_velocity_m_s: Vec3
    transfer_angle_rad: float
    iterations: int


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(vector: Vec3) -> float:
    return math.sqrt(_dot(vector, vector))


def _stumpff_c(z: float) -> float:
    if z > 1e-8:
        root = math.sqrt(z)
        return (1.0 - math.cos(root)) / z
    if z < -1e-8:
        root = math.sqrt(-z)
        return (math.cosh(root) - 1.0) / (-z)
    return 0.5 - z / 24.0 + z * z / 720.0 - z**3 / 40320.0


def _stumpff_s(z: float) -> float:
    if z > 1e-8:
        root = math.sqrt(z)
        return (root - math.sin(root)) / root**3
    if z < -1e-8:
        root = math.sqrt(-z)
        return (math.sinh(root) - root) / root**3
    return 1.0 / 6.0 - z / 120.0 + z * z / 5040.0 - z**3 / 362880.0


def solve_lambert(
    departure_position_m: Vec3,
    arrival_position_m: Vec3,
    time_of_flight_s: float,
    mu_m3_s2: float,
    *,
    prograde: bool = True,
    plane_normal: Vec3 = (0.0, 0.0, 1.0),
    tolerance_s: float = 1e-6,
    max_iterations: int = 100,
) -> LambertSolution:
    """Resuelve Lambert en 3D mediante variables universales."""
    validate_vec3(departure_position_m, "departure_position_m")
    validate_vec3(arrival_position_m, "arrival_position_m")
    validate_vec3(plane_normal, "plane_normal")
    validate_positive(time_of_flight_s, "time_of_flight_s")
    validate_positive(mu_m3_s2, "mu_m3_s2")
    validate_positive(tolerance_s, "tolerance_s")
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations <= 0:
        raise ValueError("max_iterations debe ser un entero positivo.")

    r1 = _norm(departure_position_m)
    r2 = _norm(arrival_position_m)
    normal_norm = _norm(plane_normal)
    if r1 == 0.0 or r2 == 0.0:
        raise LambertError("Las posiciones no pueden estar en el origen.")
    if normal_norm == 0.0:
        raise LambertError("plane_normal no puede ser el vector nulo.")

    cross = _cross(departure_position_m, arrival_position_m)
    sin_magnitude = _norm(cross) / (r1 * r2)
    cos_angle = max(-1.0, min(1.0, _dot(departure_position_m, arrival_position_m) / (r1 * r2)))
    if sin_magnitude <= 1e-14:
        raise LambertError("Las posiciones colineales producen una transferencia degenerada.")

    orientation = _dot(cross, plane_normal)
    direction = 1.0 if orientation >= 0.0 else -1.0
    sin_angle = sin_magnitude * (direction if prograde else -direction)
    transfer_angle = math.atan2(sin_angle, cos_angle) % (2.0 * math.pi)
    a_parameter = sin_angle * math.sqrt(r1 * r2 / (1.0 - cos_angle))
    if abs(a_parameter) <= 1e-14:
        raise LambertError("La geometría de transferencia es degenerada.")

    sqrt_mu = math.sqrt(mu_m3_s2)

    def evaluate(z: float) -> tuple[float, float] | None:
        c = _stumpff_c(z)
        s = _stumpff_s(z)
        if c <= 0.0:
            return None
        sqrt_c = math.sqrt(c)
        y = r1 + r2 + a_parameter * (z * s - 1.0) / sqrt_c
        if y < 0.0:
            return None
        sqrt_y = math.sqrt(y)
        x = sqrt_y / sqrt_c
        calculated_time = (x**3 * s + a_parameter * sqrt_y) / sqrt_mu
        return calculated_time - time_of_flight_s, y

    # t(z) es estrictamente creciente en el intervalo principal: 120 muestras + bisección
    # convergen a precisión de máquina en ~50 evaluaciones (vs >2000).
    z_min = -4.0 * math.pi**2
    z_max = 4.0 * math.pi**2 - 1e-8
    previous: tuple[float, float, float] | None = None
    bracket: tuple[float, float] | None = None
    samples = 120
    step = (z_max - z_min) / samples
    for index in range(samples + 1):
        z = z_min + step * index
        result = evaluate(z)
        if result is None or not math.isfinite(result[0]):
            continue
        value, y = result
        if value == 0.0:
            bracket = (z, z)
            break
        if previous is not None and previous[1] * value < 0.0:
            bracket = (previous[0], z)
            break
        previous = (z, value, y)

    if bracket is None:
        raise LambertError("No se pudo acotar una solución para ese tiempo de vuelo.")

    lower, upper = bracket
    iterations = 0
    while iterations < max_iterations and lower != upper:
        iterations += 1
        middle = 0.5 * (lower + upper)
        lower_result = evaluate(lower)
        middle_result = evaluate(middle)
        if lower_result is None or middle_result is None:
            raise LambertError("Falló la evaluación de las variables universales.")
        if abs(middle_result[0]) <= tolerance_s:
            lower = upper = middle
            break
        if lower_result[0] * middle_result[0] <= 0.0:
            upper = middle
        else:
            lower = middle

    z_solution = 0.5 * (lower + upper)
    final_result = evaluate(z_solution)
    if final_result is None or abs(final_result[0]) > tolerance_s:
        raise LambertError("Lambert no convergió con la tolerancia solicitada.")
    _, y = final_result

    f = 1.0 - y / r1
    g = a_parameter * math.sqrt(y / mu_m3_s2)
    g_dot = 1.0 - y / r2
    if abs(g) <= 1e-14:
        raise LambertError("La solución obtenida tiene un coeficiente g nulo.")

    departure_velocity = tuple(
        (arrival_position_m[index] - f * departure_position_m[index]) / g
        for index in range(3)
    )
    arrival_velocity = tuple(
        (g_dot * arrival_position_m[index] - departure_position_m[index]) / g
        for index in range(3)
    )
    return LambertSolution(
        departure_velocity_m_s=departure_velocity,  # type: ignore[arg-type]
        arrival_velocity_m_s=arrival_velocity,  # type: ignore[arg-type]
        transfer_angle_rad=transfer_angle,
        iterations=iterations,
    )