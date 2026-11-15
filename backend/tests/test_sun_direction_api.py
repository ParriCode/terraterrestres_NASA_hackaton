"""Dirección solar JPL sin hacer solicitudes externas en las pruebas."""
from datetime import datetime, timezone
import math

from fastapi.testclient import TestClient

from app.controllers import ephemeris_controller
from app.data.ephemeris import EphemerisError
from app.main import create_app


def test_sun_direction_uses_earth_relative_vector_in_icrf(monkeypatch):
    called = []
    def earth_position(body, at):
        called.append((body.id, at))
        return (1.0e6, 2.0e6, 0.0)
    def sun_position(at):
        called.append(("sun", at))
        return (4.0e6, 6.0e6, 0.0)
    monkeypatch.setattr(ephemeris_controller, "get_body_time_pos", earth_position)
    monkeypatch.setattr(ephemeris_controller, "get_sun_time_pos", sun_position)
    result = TestClient(create_app()).get("/ephemeris/sun-direction?date=2026-11-15T11:00:00Z")
    assert result.status_code == 200
    values = result.json()
    assert values["direction_icrf"] == [0.6, 0.8, 0.0]
    assert values["source"] == "NASA/JPL Horizons"
    assert values["frame"] == "earth_moon_barycentric_icrf"
    assert all(dt == datetime(2026,11,15,11,tzinfo=timezone.utc) for _,dt in called)
    assert {item for item,_ in called} == {"earth","sun"}


def test_sun_position_error_is_explicit(monkeypatch):
    monkeypatch.setattr(ephemeris_controller,"get_sun_time_pos",lambda _: (_ for _ in ()).throw(EphemerisError("No hay posición solar")))
    response=TestClient(create_app()).get("/ephemeris/sun-direction?date=2026-11-15T11:00:00Z")
    assert response.status_code == 502
    assert "direction_icrf" not in response.json()


def test_sun_endpoint_requires_timezone():
    response=TestClient(create_app()).get("/ephemeris/sun-direction?date=2026-11-15T11:00:00")
    assert response.status_code == 422
