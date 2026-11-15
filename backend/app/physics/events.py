"""Geometría de colisiones para el MVP Tierra-Luna.

La única clase de evento emitida en el contrato v1 es ``collision``.
Una intersección de cuerdas es una *alarma* que fuerza a reducir el paso,
no una prueba de que la trayectoria curva haya impactado.
"""

import math
from collections.abc import Sequence
from typing import Protocol

from app.models.domain import SpacecraftState, Vec3


class CollidableBody(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def radius_m(self) -> float: ...


def _vec3(value: Vec3, name: str) -> Vec3:
    if len(value) != 3 or not all(math.isfinite(v) for v in value):
        raise ValueError(f"Invalid {name}")
    return value


def is_collision(
    state: SpacecraftState,
    body_position_m: Vec3,
    body_radius_m: float,
) -> bool:
    """Verdadero si la nave toca o penetra la esfera física del cuerpo."""
    if not math.isfinite(body_radius_m) or body_radius_m <= 0:
        raise ValueError("Invalid body radius")
    r = _vec3(state.position_m, "spacecraft position")
    b = _vec3(body_position_m, "body position")
    return math.dist(r, b) <= body_radius_m


def find_colliding_body(
    state: SpacecraftState,
    body_positions_m: dict[str, Vec3],
    bodies: Sequence[CollidableBody],
) -> CollidableBody | None:
    """Devuelve el primer cuerpo que contiene la posición actual."""
    for body in bodies:
        if body.id not in body_positions_m:
            raise ValueError(f"Missing position for body: {body.id}")
        if is_collision(state, body_positions_m[body.id], body.radius_m):
            return body
    return None


# Alias de compatibilidad: código anterior del equipo importa este nombre.
_find_colliding_body = find_colliding_body


def _relative_chord(
    spacecraft_start_m: Vec3,
    spacecraft_end_m: Vec3,
    body_start_m: Vec3,
    body_end_m: Vec3,
) -> tuple[Vec3, Vec3]:
    p0 = _vec3(spacecraft_start_m, "spacecraft start")
    p1 = _vec3(spacecraft_end_m, "spacecraft end")
    b0 = _vec3(body_start_m, "body start")
    b1 = _vec3(body_end_m, "body end")
    return (
        tuple(p0[i] - b0[i] for i in range(3)),
        tuple(p1[i] - b1[i] for i in range(3)),
    )


def _closest_fraction(start: Vec3, end: Vec3) -> float:
    delta = tuple(end[i] - start[i] for i in range(3))
    length_sq = sum(v * v for v in delta)
    if not math.isfinite(length_sq):
        raise ValueError("Non-finite relative displacement")
    if length_sq == 0:
        return 0.0
    dot = sum(start[i] * delta[i] for i in range(3))
    return max(0.0, min(1.0, -dot / length_sq))


def segment_min_distance_sq(
    spacecraft_start_m: Vec3,
    spacecraft_end_m: Vec3,
    body_start_m: Vec3,
    body_end_m: Vec3,
) -> float:
    """Distancia mínima al cuadrado de la cuerda nave-cuerpo *relativa*.

    Se aproximan linealmente ambos movimientos SOLO para identificar
    posibles cruces que requieren integración con un paso más pequeño.
    """
    start, end = _relative_chord(
        spacecraft_start_m, spacecraft_end_m, body_start_m, body_end_m
    )
    f = _closest_fraction(start, end)
    closest = tuple(start[i] + f * (end[i] - start[i]) for i in range(3))
    result = sum(v * v for v in closest)
    if not math.isfinite(result):
        raise ValueError("Non-finite minimum distance")
    return result


def swept_collision_closest_fraction(
    spacecraft_start_m: Vec3,
    spacecraft_end_m: Vec3,
    body_start_m: Vec3,
    body_end_m: Vec3,
    body_radius_m: float,
) -> float | None:
    """Fracción de máxima aproximación de la cuerda, si cruza la esfera.

    Compatibilidad con la implementación original de ORBITAL4B. NO equivale a
    la fracción de primer impacto ni certifica el evento orbital real.
    """
    if not math.isfinite(body_radius_m) or body_radius_m <= 0:
        raise ValueError("Invalid body radius")
    start, end = _relative_chord(
        spacecraft_start_m, spacecraft_end_m, body_start_m, body_end_m
    )
    fraction = _closest_fraction(start, end)
    closest = tuple(start[i] + fraction * (end[i] - start[i]) for i in range(3))
    dist = math.hypot(*closest)
    if not math.isfinite(dist):
        raise ValueError("Non-finite closest distance")
    return fraction if dist <= body_radius_m else None