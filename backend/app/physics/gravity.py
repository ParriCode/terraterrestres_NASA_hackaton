"""Aceleración gravitatoria."""

import math
from collections.abc import Sequence
from typing import Protocol
from app.models.domain import Vec3


class GravitatingBody(Protocol):
    """Propiedades que necesita la gravedad, sin depender del proveedor orbital."""

    @property
    def id(self) -> str: ...

    @property
    def mu_m3_s2(self) -> float: ...

    @property
    def radius_m(self) -> float: ...

class GravityError(ValueError):
    """Error al calcular la aceleración gravitatoria."""
    pass

"""
!Recibe estado de la nave y posición de los cuerpos, junto con sus instancias, calcula la aceleración que siente la nave en ese instante según la ley de gravitación universal de Newton
@param state Estado actual de la nave espacia
@param body_positions_m Hash table para asociar cuerpo con su posición
@param bodies Lista de las instancias de los cuerpos
@return Vec3 Vector de la aceleración que recibe la nave
"""
def gravitational_acceleration(
    spacecraft_position_m: Vec3,
    body_positions_m: dict[str, Vec3],
    bodies: Sequence[GravitatingBody],
) -> Vec3:
    ax = ay = az = 0.0

    for body in bodies:
        if body.id not in body_positions_m:
            raise GravityError(
                f"Missing position for body: {body.id}"
            )
        bx, by, bz = body_positions_m[body.id]

        # Calcula el vector diferencia entre la nave y el cuerpo
        dx = spacecraft_position_m[0] - bx
        dy = spacecraft_position_m[1] - by
        dz = spacecraft_position_m[2] - bz

        distance_sq = dx*dx + dy*dy + dz*dz

        if not math.isfinite(distance_sq):
            raise GravityError("Non-finite distance")

        if distance_sq <= 0.0:
            raise GravityError(
                f"Spacecraft at center of {body.id}"
            )

        distance = math.sqrt(distance_sq)

        if distance < body.radius_m:
            raise GravityError(
                f"Spacecraft inside {body.id}"
            )

        # Cálculo de la aceleración para cada coordenada
        factor = -body.mu_m3_s2 / (distance_sq * distance)

        ax += factor * dx
        ay += factor * dy
        az += factor * dz

    result = (ax, ay, az)

    if not all(math.isfinite(v) for v in result):
        raise GravityError("Invalid acceleration")

    return result
