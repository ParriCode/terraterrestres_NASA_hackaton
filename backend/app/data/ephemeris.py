"""Posiciones geométricas de Horizons, en metros respecto al baricentro Tierra–Luna.

Referencia: https://ssd-api.jpl.nasa.gov/doc/horizons.html
Las fechas de entrada son datetime con zona horaria; se consultan en UTC.
Usa una caché maestra por ventanas de 35 días con interpolación de Hermite cúbica
para evitar peticiones HTTP repetidas durante barridos de optimización.
"""

import csv
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import io
import json
import math
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
from scipy.interpolate import CubicHermiteSpline

from app.config.bodies import CELESTIAL_BODIES, HORIZONS_API_URL, HORIZONS_TIMEOUT_S
from app.models.domain import CelestialBody, Vec3

_MASTER_STEP_S = 600.0
_MIN_MASTER_DAYS = 35


class EphemerisError(RuntimeError):
    """No ha sido posible obtener una posición válida de Horizons."""


def _horizons_id_for(body: CelestialBody) -> str:
    config = next((item for item in CELESTIAL_BODIES if item.id == body.id), None)
    if config is None:
        raise ValueError(f"Cuerpo sin identificador Horizons configurado: {body.id}")
    return config.horizons_id


def _http_get_json(params: dict[str, str]) -> dict:
    url = f"{HORIZONS_API_URL}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "Orbital4B/1.0 (NASA-Hackathon)"})
    with urlopen(req, timeout=HORIZONS_TIMEOUT_S) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise EphemerisError("Horizons devolvió una respuesta inesperada.")
    if payload.get("error"):
        raise EphemerisError(str(payload["error"]))
    return payload


@lru_cache(maxsize=32)
def _fetch_master_spline(
    horizons_id: str,
    window_start_ts: float,
    span_days: int,
) -> tuple[float, float, CubicHermiteSpline]:
    """Descarga una única tabla cada 600 s y construye un spline C1 continuo."""
    duration_s = float(span_days * 86400)
    intervals = int(round(duration_s / _MASTER_STEP_S))
    start_jd = window_start_ts / 86400.0 + 2440587.5
    stop_jd = (window_start_ts + duration_s) / 86400.0 + 2440587.5

    params = {
        "format": "json",
        "COMMAND": horizons_id,
        "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "VECTORS",
        "CENTER": "500@3",
        "REF_SYSTEM": "ICRF",
        "REF_PLANE": "FRAME",
        "TIME_TYPE": "UT",
        "OUT_UNITS": "KM-S",
        "VEC_TABLE": "2",
        "VEC_CORR": "NONE",
        "CSV_FORMAT": "YES",
        "START_TIME": f"'JD{start_jd:.10f}'",
        "STOP_TIME": f"'JD{stop_jd:.10f}'",
        "STEP_SIZE": str(intervals),
    }
    try:
        payload = _http_get_json(params)
        table = payload["result"].split("$$SOE", 1)[1].split("$$EOE", 1)[0].strip()
        rows = list(csv.reader(io.StringIO(table)))
        if len(rows) != intervals + 1:
            raise ValueError("Horizons no devolvió todos los intervalos esperados.")

        positions = np.empty((len(rows), 3), dtype=np.float64)
        velocities = np.empty((len(rows), 3), dtype=np.float64)
        for idx, row in enumerate(rows):
            vals = [float(v.replace("D", "E")) * 1000.0 for v in row[2:8]]
            if len(vals) != 6 or not all(math.isfinite(v) for v in vals):
                raise ValueError("Estado inválido en tabla Horizons.")
            positions[idx] = vals[:3]
            velocities[idx] = vals[3:]

        times = np.linspace(0.0, duration_s, len(rows), dtype=np.float64)
        spline = CubicHermiteSpline(times, positions, velocities, extrapolate=False)
        return window_start_ts, duration_s, spline
    except (URLError, TimeoutError, OSError, ValueError, KeyError, IndexError) as error:
        raise EphemerisError(f"Error obteniendo tabla Horizons: {error}") from error


def _get_window_spline(
    horizons_id: str,
    start_utc: datetime,
    stop_utc: datetime,
) -> tuple[float, CubicHermiteSpline]:
    day_floor = start_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    window_start_ts = day_floor.timestamp()
    needed_days = math.ceil((stop_utc.timestamp() - window_start_ts) / 86400.0) + 1
    span_days = max(_MIN_MASTER_DAYS, needed_days)
    base_ts, _, spline = _fetch_master_spline(horizons_id, window_start_ts, span_days)
    return base_ts, spline


def get_body_state_table(
    body: CelestialBody,
    start: datetime,
    stop: datetime,
    intervals: int,
) -> tuple[tuple[float, ...], tuple[Vec3, ...], tuple[Vec3, ...]]:
    """Tabla uniforme (segundos, posiciones SI, velocidades SI) sin peticiones redundantes."""
    if start.utcoffset() is None or stop.utcoffset() is None or stop <= start:
        raise ValueError("Se requieren fechas ordenadas con zona horaria.")
    if not 2 <= intervals <= 10000:
        raise ValueError("intervals debe estar entre 2 y 10000.")

    horizons_id = _horizons_id_for(body)
    start_utc = start.astimezone(timezone.utc)
    stop_utc = stop.astimezone(timezone.utc)
    base_ts, spline = _get_window_spline(horizons_id, start_utc, stop_utc)

    duration = (stop_utc - start_utc).total_seconds()
    rel_times = np.linspace(0.0, duration, intervals + 1, dtype=np.float64)
    query_times = (start_utc.timestamp() - base_ts) + rel_times

    pos_arr = spline(query_times)
    vel_arr = spline(query_times, 1)

    times = tuple(float(t) for t in rel_times)
    positions = tuple((float(p[0]), float(p[1]), float(p[2])) for p in pos_arr)
    velocities = tuple((float(v[0]), float(v[1]), float(v[2])) for v in vel_arr)
    return times, positions, velocities


def get_body_time_pos(body: CelestialBody, time: datetime) -> Vec3:
    """Devuelve (x, y, z) en metros, con origen 500@3 y ejes ICRF."""
    return _get_body_state(body, time)[0]


def get_body_time_velocity(body: CelestialBody, time: datetime) -> Vec3:
    """Vector de velocidad geométrica en m/s, con el mismo marco que la posición."""
    return _get_body_state(body, time)[1]


def _get_body_state(body: CelestialBody, time: datetime) -> tuple[Vec3, Vec3]:
    if not isinstance(time, datetime):
        raise TypeError("time debe ser un datetime con zona horaria.")
    if time.utcoffset() is None:
        raise ValueError("time debe incluir zona horaria.")

    horizons_id = _horizons_id_for(body)
    instant_utc = time.astimezone(timezone.utc)
    base_ts, spline = _get_window_spline(
        horizons_id, instant_utc, instant_utc + timedelta(seconds=60)
    )
    tau = instant_utc.timestamp() - base_ts
    p = spline(tau)
    v = spline(tau, 1)
    return (float(p[0]), float(p[1]), float(p[2])), (float(v[0]), float(v[1]), float(v[2]))