"""Vista astronómica Tierra–Luna en ejes ICRF fijos, sin simular la nave."""

from datetime import timezone

from fastapi import APIRouter, HTTPException
from pydantic import AwareDatetime

from app.data.bodies import load_bodies
from app.data.ephemeris import EphemerisError, get_body_time_pos

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
