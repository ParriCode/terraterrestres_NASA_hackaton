"""Detección de impactos y encuentros."""

import math
from app.models.domain import CelestialBody, SpacecraftState, Vec3
from collections.abc import Sequence
from typing import Protocol

class CollidableBody(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def radius_m(self) -> float: ...

"""
Recibe posición y cuerpos
@return Si hay colisión dado un estado de la name
"""
def is_collision(
    state: SpacecraftState,
    body_position_m: Vec3,
    body_radius_m: float,
) -> bool:
    if not math.isfinite(body_radius_m) or body_radius_m <= 0:
        raise ValueError("Invalid body radius")

    spacecraft_position_m = state.position_m
    distance = math.dist(
        spacecraft_position_m,
        body_position_m,
    )

    if not math.isfinite(distance):
        raise ValueError("Non-finite distance")

    return distance <= body_radius_m

"""
!Dado un estado actual de Spacecraft, posiciones de los cuerpos junto con sus instancias, mira si hay colisión
@return El cuerpo que colisiona o ninguno
"""
def find_colliding_body(
    state: SpacecraftState,
    body_positions_m: dict[str, Vec3],
    bodies: list[CollidableBody],
) -> CollidableBody | None:

    for body in bodies:
        if body.id not in body_positions_m:
            raise ValueError(
                f"Missing position for body: {body.id}"
            )

        if is_collision(
            state,
            body_positions_m[body.id],
            body.radius_m,
        ):
            return body

    return None

"""
Comprueba si el segmento relativo nave-cuerpo atraviesa la esfera
Devuelve la fracción del segmento correspondiente al punto de
máximo acercamiento, o None si el segmento no intersecta la esfera
@param spacecraft_start_m Posición inicial de la nave
@param spacecraft_end_m Posición final de la nave
@param body_start_m Posición inicial del cuerpo
@param body_end_m Posición final del cuerpo
@param body_radius_m Radio del cuerpo
@return Fracción del tiempo más cercano a la colisión o nada
"""
def swept_collision_closest_fraction(
    spacecraft_start_m: Vec3,
    spacecraft_end_m: Vec3,
    body_start_m: Vec3,
    body_end_m: Vec3,
    body_radius_m: float,
) -> float | None:

    if not math.isfinite(body_radius_m) or body_radius_m <= 0:
        raise ValueError("Invalid body radius")
    
    relative_start = tuple(
        spacecraft_start_m[i] - body_start_m[i]
        for i in range(3)
    )

    relative_end = tuple(
        spacecraft_end_m[i] - body_end_m[i]
        for i in range(3)
    )

    delta = tuple(
        relative_end[i] - relative_start[i]
        for i in range(3)
    )

    delta_sq = sum(component**2 for component in delta)

    if not math.isfinite(delta_sq):
        raise ValueError("Non-finite relative displacement")

    if delta_sq == 0.0:
        fraction = 0.0
    else:
        dot_product = sum(
            relative_start[i] * delta[i]
            for i in range(3)
        )

        fraction = max(
            0.0,
            min(1.0, -dot_product / delta_sq),
        )

    closest_point = tuple(
        relative_start[i] + fraction * delta[i]
        for i in range(3)
    )

    closest_distance = math.hypot(*closest_point)

    if not math.isfinite(closest_distance):
        raise ValueError("Non-finite closest distance")

    if closest_distance <= body_radius_m:
        return fraction

    return None