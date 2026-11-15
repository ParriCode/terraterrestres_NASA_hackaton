"""Vista astronómica Tierra–Luna en ejes ICRF fijos, sin simular la nave."""

from datetime import timezone
import math

from fastapi import APIRouter, HTTPException
from pydantic import AwareDatetime

from app.data.bodies import load_bodies
from app.data.ephemeris import EphemerisError, get_body_time_pos, get_sun_time_pos

router = APIRouter(prefix="/ephemeris", tags=["Efemérides"])


@router.get("/earth-moon")
def earth_moon_at(date: AwareDatetime):
    """Devuelve posiciones geométricas NASA/JPL en metros, centro 500@3.

    La orientación ICRF es fija entre consultas. No rota el eje X hacia la Luna.
    """
    utc_date = date.astimezone(timezone.utc)
    bodies = load_bodies()
    try:
        positions = {
            key: get_body_time_pos(bodies[key], utc_date)
            for key in ("earth", "moon")
        }
    except (EphemerisError, OSError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "source": "NASA/JPL Horizons",
        "date": utc_date,
        "frame": "earth_moon_barycentric_icrf",
        "center": "500@3",
        "units": "m",
        "body_positions_m": positions,
    }


@router.get("/sun-direction")
def sun_direction_at(date: AwareDatetime):
    """Vector unitario Tierra → Sol en ICRF a la fecha UTC solicitada.

    El Sol está fuera de la escala Tierra-Luna: solamente se dibuja su dirección
    en el frontend. No se aproxima su posición con un dato inventado.
    """
    utc_date = date.astimezone(timezone.utc)
    try:
        earth = get_body_time_pos(load_bodies()["earth"], utc_date)
        sun = get_sun_time_pos(utc_date)
        direction = tuple(s - e for s, e in zip(sun, earth))
        length = math.sqrt(sum(v * v for v in direction))
        if not math.isfinite(length) or length <= 0 or not all(math.isfinite(v) for v in direction):
            raise EphemerisError("Horizons devolvió un vector solar no válido.")
    except (EphemerisError, OSError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "source": "NASA/JPL Horizons",
        "date": utc_date,
        "frame": "earth_moon_barycentric_icrf",
        "from": "earth",
        "toward": "sun",
        "direction_icrf": tuple(value / length for value in direction),
    }
