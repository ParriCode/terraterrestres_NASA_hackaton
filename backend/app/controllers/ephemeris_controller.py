"""Vista astronómica Tierra–Luna en ejes ICRF fijos, sin simular la nave."""

from datetime import timezone
import math

from fastapi import APIRouter, HTTPException, Request
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



@router.get('/sun-direction')
def sun_direction_at(date: AwareDatetime):
    """Vector unitario Tierra → Sol, ambas posiciones JPL en el marco ICRF 500@3.

    Es una dirección (no un punto): el Sol se dibuja fuera de escala.
    """
    from pathlib import Path
    from app.data.ephemeris import _fetch_state

    instant = date.astimezone(timezone.utc)
    try:
        bodies = load_bodies()
        earth = get_body_time_pos(bodies['earth'], instant)
        sun = _fetch_state('10', instant, center='500@3')[0]
        v = tuple(s - e for s, e in zip(sun, earth))
        r = math.hypot(*v)
        if not (r > 0 and math.isfinite(r)):
            raise EphemerisError('Vector solar JPL inválido')
    except (EphemerisError, OSError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        'source': 'NASA/JPL Horizons', 'date': instant,
        'frame': 'earth_moon_barycentric_icrf',
        'from': 'earth', 'toward': 'sun',
        'direction_icrf': tuple(x / r for x in v),
    }

@router.get('/solar')
def solar_at(date: AwareDatetime):
    from pathlib import Path
    import math
    from app.data.ephemeris import _fetch_state
    catalog = load_bodies(Path(__file__).parents[1] / 'data' / 'solar_bodies.json')
    from app.config.bodies import CELESTIAL_BODIES
    ids = {b.id: b.horizons_id for b in CELESTIAL_BODIES}
    eps = math.radians(23.439291111)
    try:
        positions = {}
        for key in catalog:
            x, y, z = _fetch_state(ids[key], date.astimezone(timezone.utc), center='500@0')[0]
            positions[key] = [x, y * math.cos(eps) + z * math.sin(eps), 0.0]
    except EphemerisError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {'source': 'NASA/JPL Horizons', 'date': date, 'center': '500@0',
            'frame': 'ssb_ecliptic_j2000_projected', 'units': 'm', 'body_positions_m': positions}


@router.get('/solar-day')
async def solar_day(date: AwareDatetime, request: Request):
    """Stream daily NASA tables; browsers interpolate without requesting each frame."""
    from datetime import timedelta
    import json
    from pathlib import Path
    from fastapi.responses import StreamingResponse
    from starlette.concurrency import run_in_threadpool
    from app.data.ephemeris import get_body_state_table

    start = date.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    catalog = load_bodies(Path(__file__).parents[1] / 'data' / 'solar_bodies.json')

    async def rows():
        # Sun first anchors the map; Earth and Moon appear next.
        for key in ('sun', 'earth', 'moon', 'mercury', 'venus', 'mars', 'jupiter', 'saturn', 'uranus', 'neptune'):
            if await request.is_disconnected():
                return
            try:
                times, positions, velocities = await run_in_threadpool(
                    get_body_state_table, catalog[key], start, start + timedelta(days=1), 24, center='500@0')
                yield json.dumps({'body_id': key, 'date': start.isoformat(), 'source': 'NASA/JPL Horizons',
                    'frame': 'ssb_icrf', 'times_s': times, 'positions_m': positions,
                    'velocities_m_s': velocities}) + '\n'
            except (EphemerisError, OSError) as exc:
                yield json.dumps({'error': str(exc)}) + '\n'
                return

    return StreamingResponse(rows(), media_type='application/x-ndjson',
        headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
