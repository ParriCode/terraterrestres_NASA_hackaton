"""Contrato y fallo explícito de la vista previa sin tráfico NASA real."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.controllers import ephemeris_controller
from app.data.ephemeris import EphemerisError


def test_earth_moon_uses_selected_date_and_real_positions(monkeypatch):
    called = []

    def fake_position(body, at):
        called.append((body.id, at))
        return (1.0, 2.0, 3.0) if body.id == "earth" else (40.0, 50.0, 60.0)

    monkeypatch.setattr(ephemeris_controller, "get_body_time_pos", fake_position)
    client = TestClient(create_app())
    response = client.get("/ephemeris/earth-moon?date=2026-11-14T20%3A00%3A00%2B01%3A00")
    assert response.status_code == 200
    result = response.json()
    assert result["frame"] == "earth_moon_barycentric_icrf"
    assert result["body_positions_m"] == {"earth": [1, 2, 3], "moon": [40, 50, 60]}
    assert {key for key, _ in called} == {"earth", "moon"}
    assert all(at == datetime(2026, 11, 14, 19, tzinfo=timezone.utc) for _, at in called)
    assert result["source"] == "NASA/JPL Horizons"


def test_failure_does_not_fabricate_position(monkeypatch):
    def fake_error(*args):
        raise EphemerisError("Sin cobertura o servicio indisponible")
    monkeypatch.setattr(ephemeris_controller, "get_body_time_pos", fake_error)
    response = TestClient(create_app()).get("/ephemeris/earth-moon?date=2026-11-14T19:00:00Z")
    assert response.status_code == 502
    assert "body_positions_m" not in response.json()


def test_requires_tz_aware_date():
    response = TestClient(create_app()).get("/ephemeris/earth-moon?date=2026-11-14T19:00:00")
    assert response.status_code == 422


def test_date_change_changes_renderable_position(monkeypatch):
    def fake_position(body, at):
        if body.id == "earth":
            return (0.0, 0.0, 0.0)
        if at.day == 14:
            return (384_400_000.0, 0.0, 0.0)
        return (0.0, 384_400_000.0, 0.0)

    monkeypatch.setattr(ephemeris_controller, "get_body_time_pos", fake_position)
    client = TestClient(create_app())
    first = client.get("/ephemeris/earth-moon?date=2026-11-14T19:00:00Z").json()
    second = client.get("/ephemeris/earth-moon?date=2026-11-15T19:00:00Z").json()
    assert first["body_positions_m"]["moon"] != second["body_positions_m"]["moon"]
    assert first["frame"] == second["frame"] == "earth_moon_barycentric_icrf"
