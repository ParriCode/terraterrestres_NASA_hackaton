"""Aceleracion gravitatoria newtoniana (unidades SI)."""

import math
from collections.abc import Sequence
from typing import Protocol

from app.mission.models.domain import Vec3


class GravitatingBody(Protocol):
    """Datos minimos de CelestialBody requeridos por el modelo gravitatorio."""

    @property
    def id(self) -> str: ...

    @property
    def mu_m3_s2(self) -> float: ...

    @property
    def radius_m(self) -> float: ...


class GravityError(ValueError):
    """No es posible evaluar una aceleracion gravitatoria valida."""


def gravitational_acceleration(
    spacecraft_position_m: Vec3,
    body_positions_m: dict[str, Vec3],
    bodies: Sequence[GravitatingBody],
    *,
    check_surface: bool = True,
) -> Vec3:
    """Calcula -sum(mu * (r-r_i) / |r-r_i|**3).

    Por defecto la nave no puede estar dentro de los radios fisicos. Shooting
    puede desactivar check_surface para evaluar candidatas provisionales;
    la validación de colisiones se hace después de resolver el contorno.
    """
    if len(spacecraft_position_m) != 3 or not all(
        math.isfinite(value) for value in spacecraft_position_m
    ):
        raise GravityError("Invalid spacecraft position")

    ax = ay = az = 0.0
    for body in bodies:
        if body.id not in body_positions_m:
            raise GravityError(f"Missing position for body: {body.id}")
        if (
            not math.isfinite(body.mu_m3_s2)
            or body.mu_m3_s2 <= 0
            or not math.isfinite(body.radius_m)
            or body.radius_m <= 0
        ):
            raise GravityError(f"Invalid gravitational body: {body.id}")

        body_position = body_positions_m[body.id]
        if len(body_position) != 3 or not all(math.isfinite(v) for v in body_position):
            raise GravityError(f"Invalid body position: {body.id}")

        dx = spacecraft_position_m[0] - body_position[0]
        dy = spacecraft_position_m[1] - body_position[1]
        dz = spacecraft_position_m[2] - body_position[2]
        distance_sq = dx * dx + dy * dy + dz * dz
        if not math.isfinite(distance_sq) or distance_sq <= 0:
            raise GravityError(f"Invalid distance to {body.id}")

        distance = math.sqrt(distance_sq)
        if check_surface and distance < body.radius_m:
            raise GravityError(f"Spacecraft inside {body.id}")

        factor = -body.mu_m3_s2 / (distance_sq * distance)
        ax += factor * dx
        ay += factor * dy
        az += factor * dz

    result = (ax, ay, az)
    if not all(math.isfinite(value) for value in result):
        raise GravityError("Non-finite acceleration")
    return result
