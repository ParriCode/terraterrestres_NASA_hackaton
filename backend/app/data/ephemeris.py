"""Posiciones geométricas de Horizons, en metros respecto al baricentro Tierra–Luna.

Referencia: https://ssd-api.jpl.nasa.gov/doc/horizons.html
Las fechas de entrada son datetime con zona horaria; se consultan en UTC.
"""

import csv
from datetime import datetime, timezone
from functools import lru_cache
import io
import json
import math
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from app.config.bodies import CELESTIAL_BODIES, HORIZONS_API_URL, HORIZONS_TIMEOUT_S
from app.models.domain import CelestialBody, Vec3


class EphemerisError(RuntimeError):
    """No ha sido posible obtener una posición válida de Horizons."""


def get_body_time_pos(body: CelestialBody, time: datetime) -> Vec3:
    """Devuelve (x, y, z) en metros, con origen 500@3 y ejes ICRF.

    No aplica correcciones de tiempo de luz. Las consultas repetidas se guardan
    en memoria; una fecha nueva requiere una petición a Horizons.
    """
    if not isinstance(time, datetime):
        raise TypeError("time debe ser un datetime con zona horaria.")
    if time.utcoffset() is None:
        raise ValueError("time debe incluir zona horaria.")
    config = next((item for item in CELESTIAL_BODIES if item.id == body.id), None)
    if config is None:
        raise ValueError(f"Cuerpo sin identificador Horizons configurado: {body.id}")
    return _fetch_position(config.horizons_id, time.astimezone(timezone.utc))


@lru_cache(maxsize=2048)
def _fetch_position(horizons_id: str, instant: datetime) -> Vec3:
    julian_day = instant.timestamp() / 86400.0 + 2440587.5
    params = {
        "format": "json", "COMMAND": horizons_id,
        "OBJ_DATA": "NO", "MAKE_EPHEM": "YES", "EPHEM_TYPE": "VECTORS",
        "CENTER": "500@3", "REF_SYSTEM": "ICRF", "REF_PLANE": "FRAME",
        "TIME_TYPE": "UT", "TLIST": f"{julian_day:.10f}", "TLIST_TYPE": "JD",
        "OUT_UNITS": "KM-S", "VEC_TABLE": "1", "VEC_CORR": "NONE",
        "CSV_FORMAT": "YES",
    }
    try:
        with urlopen(
            f"{HORIZONS_API_URL}?{urlencode(params)}", timeout=HORIZONS_TIMEOUT_S
        ) as response:
            payload = json.load(response)
    except (URLError, TimeoutError, OSError, ValueError) as error:
        raise EphemerisError(f"Error consultando Horizons: {error}") from error
    if not isinstance(payload, dict):
        raise EphemerisError("Horizons devolvió una respuesta inesperada.")
    if payload.get("error"):
        raise EphemerisError(str(payload["error"]))
    return _parse_position(payload.get("result", ""))


def _parse_position(result: str) -> Vec3:
    try:
        table = result.split("$$SOE", 1)[1].split("$$EOE", 1)[0].strip()
        rows = list(csv.reader(io.StringIO(table)))
        if len(rows) != 1:
            raise ValueError("Se esperaba una única muestra.")
        position = tuple(float(value.replace("D", "E")) * 1000 for value in rows[0][2:5])
        if len(position) != 3 or not all(math.isfinite(value) for value in position):
            raise ValueError("Vector de posición inválido.")
        return position
    except (AttributeError, IndexError, TypeError, ValueError) as error:
        raise EphemerisError("No se pudo interpretar la posición de Horizons.") from error
