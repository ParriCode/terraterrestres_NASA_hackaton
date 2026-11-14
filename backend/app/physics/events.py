"""Detección de impactos y encuentros."""

import math
from app.models.domain import CelestialBody, SpacecraftState, Vec3

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
    dx = spacecraft_position_m[0] - body_position_m[0]
    dy = spacecraft_position_m[1] - body_position_m[1]
    dz = spacecraft_position_m[2] - body_position_m[2]

    distance_sq = dx*dx + dy*dy + dz*dz

    if not math.isfinite(distance_sq):
        raise ValueError("Non-finite distance")

    return distance_sq <= body_radius_m**2
