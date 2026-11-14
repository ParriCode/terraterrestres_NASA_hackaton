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


@lru_cache(maxsize=16)
def get_body_state_table(body: CelestialBody, start: datetime, stop: datetime,
                         intervals: int) -> tuple:
    """Tabla uniforme (segundos, posiciones SI, velocidades SI), una petición.

    STEP_SIZE sin unidades indica el número de intervalos entre ambos extremos.
    """
    if start.utcoffset() is None or stop.utcoffset() is None or stop <= start:
        raise ValueError("Se requieren fechas ordenadas con zona horaria.")
    if not 2 <= intervals <= 10000:
        raise ValueError("intervals debe estar entre 2 y 10000.")
    config = next(item for item in CELESTIAL_BODIES if item.id == body.id)
    params = {
        "format": "json", "COMMAND": config.horizons_id,
        "OBJ_DATA": "NO", "MAKE_EPHEM": "YES", "EPHEM_TYPE": "VECTORS",
        "CENTER": "500@3", "REF_SYSTEM": "ICRF", "REF_PLANE": "FRAME",
        "TIME_TYPE": "UT", "OUT_UNITS": "KM-S", "VEC_TABLE": "2",
        "VEC_CORR": "NONE", "CSV_FORMAT": "YES",
        "START_TIME": "'JD%.10f'" % (start.timestamp() / 86400 + 2440587.5),
        "STOP_TIME": "'JD%.10f'" % (stop.timestamp() / 86400 + 2440587.5),
        "STEP_SIZE": str(intervals),
    }
    try:
        with urlopen(f"{HORIZONS_API_URL}?{urlencode(params)}",
                     timeout=HORIZONS_TIMEOUT_S) as response:
            payload = json.load(response)
        if payload.get("error"):
            raise ValueError(payload["error"])
        table = payload["result"].split("$$SOE", 1)[1].split("$$EOE", 1)[0].strip()
        rows = list(csv.reader(io.StringIO(table)))
        positions, velocities = [], []
        for row in rows:
            values = tuple(float(v.replace("D", "E")) * 1000 for v in row[2:8])
            if len(values) != 6 or not all(math.isfinite(v) for v in values):
                raise ValueError("Estado inválido en tabla Horizons.")
            positions.append(values[:3])
            velocities.append(values[3:])
        if len(rows) != intervals + 1:
            raise ValueError("Horizons no devolvió todos los intervalos.")
        duration = (stop - start).total_seconds()
        times = tuple(duration * i / intervals for i in range(intervals + 1))
        return times, tuple(positions), tuple(velocities)
    except (URLError, TimeoutError, OSError, ValueError, KeyError, IndexError) as error:
        raise EphemerisError(f"Error obteniendo tabla Horizons: {error}") from error


def get_body_time_pos(body: CelestialBody, time: datetime) -> Vec3:
    """Devuelve (x, y, z) en metros, con origen 500@3 y ejes ICRF.

    No aplica correcciones de tiempo de luz. Las consultas repetidas se guardan
    en memoria; una fecha nueva requiere una petición a Horizons.
    """
    return _get_body_state(body, time)[0]


def get_body_time_velocity(body: CelestialBody, time: datetime) -> Vec3:
    """Vector de velocidad geométrica en m/s, con el mismo marco que la posición."""
    return _get_body_state(body, time)[1]


def _get_body_state(body: CelestialBody, time: datetime) -> tuple[Vec3, Vec3]:
    if not isinstance(time, datetime):
        raise TypeError("time debe ser un datetime con zona horaria.")
    if time.utcoffset() is None:
        raise ValueError("time debe incluir zona horaria.")
    config = next((item for item in CELESTIAL_BODIES if item.id == body.id), None)
    if config is None:
        raise ValueError(f"Cuerpo sin identificador Horizons configurado: {body.id}")
    return _fetch_state(config.horizons_id, time.astimezone(timezone.utc))


@lru_cache(maxsize=2048)
def _fetch_state(horizons_id: str, instant: datetime) -> tuple[Vec3, Vec3]:
    julian_day = instant.timestamp() / 86400.0 + 2440587.5
    params = {
        "format": "json", "COMMAND": horizons_id,
        "OBJ_DATA": "NO", "MAKE_EPHEM": "YES", "EPHEM_TYPE": "VECTORS",
        "CENTER": "500@3", "REF_SYSTEM": "ICRF", "REF_PLANE": "FRAME",
        "TIME_TYPE": "UT", "TLIST": f"{julian_day:.10f}", "TLIST_TYPE": "JD",
        "OUT_UNITS": "KM-S", "VEC_TABLE": "2", "VEC_CORR": "NONE",
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
    return _parse_state(payload.get("result", ""))


def _parse_state(result: str) -> tuple[Vec3, Vec3]:
    try:
        table = result.split("$$SOE", 1)[1].split("$$EOE", 1)[0].strip()
        rows = list(csv.reader(io.StringIO(table)))
        if len(rows) != 1:
            raise ValueError("Se esperaba una única muestra.")
        values = [float(value.replace("D", "E")) * 1000 for value in rows[0][2:8]]
        if len(values) != 6 or not all(math.isfinite(value) for value in values):
            raise ValueError("Estado inválido.")
        return (values[0], values[1], values[2]), (values[3], values[4], values[5])
    except (AttributeError, IndexError, TypeError, ValueError) as error:
        raise EphemerisError("No se pudo interpretar la posición de Horizons.") from error
