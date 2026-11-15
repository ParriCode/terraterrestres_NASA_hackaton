"""Comprobar el indicador solar sin acceder a NASA durante las pruebas."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.controllers import ephemeris_controller
from app.data import ephemeris
from app.data.ephemeris import EphemerisError
from app.main import create_app


def test_sun_direction_earth_to_sun_is_icrf_and_normalized(monkeypatch):
    calls = []

    def earth_state(_body, instant):
        calls.append(('earth', instant))
        return (1.0e6, 2.0e6, 0.0)

    def sun_state(code, instant, center):
        calls.append((code, instant, center))
        return (4.0e6, 6.0e6, 0.0), (0.0, 0.0, 0.0)

    monkeypatch.setattr(ephemeris_controller, 'get_body_time_pos', earth_state)
    monkeypatch.setattr(ephemeris, '_fetch_state', sun_state)
    result = TestClient(create_app()).get('/ephemeris/sun-direction?date=2026-11-15T11:00:00Z')
    assert result.status_code == 200
    value = result.json()
    assert value['direction_icrf'] == [0.6, 0.8, 0.0]
    assert value['frame'] == 'earth_moon_barycentric_icrf'
    assert calls == [('earth', datetime(2026,11,15,11,tzinfo=timezone.utc)),
                     ('10', datetime(2026,11,15,11,tzinfo=timezone.utc), '500@3')]


def test_sun_error_is_reported_as_502(monkeypatch):
    def fail(*_args, **_kwargs):
        raise EphemerisError('No hay dato JPL')
    monkeypatch.setattr(ephemeris, '_fetch_state', fail)
    result = TestClient(create_app()).get('/ephemeris/sun-direction?date=2026-11-15T11:00:00Z')
    assert result.status_code == 502


def test_sun_rejects_naive_dates():
    result = TestClient(create_app()).get('/ephemeris/sun-direction?date=2026-11-15T11:00:00')
    assert result.status_code == 422
