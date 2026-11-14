"""Pruebas de contrato API para /transfers/optimize y compatibilidad con /transfers."""
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.data.bodies import load_bodies
from app.data.ephemeris import EphemerisError
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def circular_ephemeris(monkeypatch):
    catalog = load_bodies()
    mu_t, mu_l = (catalog[k].mu_m3_s2 for k in ("earth", "moon"))
    distance = 384400000.0
    omega = np.sqrt((mu_t + mu_l) / distance**3)

    def table(body, start, stop, intervals):
        times = np.linspace(0, (stop - start).total_seconds(), intervals + 1)
        radius = -distance * mu_l / (mu_t + mu_l) if body.id == "earth" else distance * mu_t / (mu_t + mu_l)
        positions = np.column_stack((radius * np.cos(omega * times),
                                     radius * np.sin(omega * times), np.zeros_like(times)))
        velocities = np.column_stack((-radius * omega * np.sin(omega * times),
                                      radius * omega * np.cos(omega * times), np.zeros_like(times)))
        return times, positions, velocities

    monkeypatch.setattr("app.data.ephemeris.get_body_state_table", table)


def test_optimize_endpoint_returns_ok_with_delta_v_and_tradeoff(client, circular_ephemeris):
    response = client.post(
        "/transfers/optimize",
        json={
            "date": "2026-11-14T00:00:00Z",
            "max_duration_s": 10 * 86400,
            "parking_alt_m": 200_000,
            "samples": 10,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["duration_s"] <= 10 * 86400
    assert data["max_duration_s"] == 10 * 86400
    assert data["parking_alt_m"] == 200_000
    assert data["launch_delta_v_m_s"] > 0
    assert data["arrival_delta_v_m_s"] > 0
    assert data["total_delta_v_m_s"] == pytest.approx(
        data["launch_delta_v_m_s"] + data["arrival_delta_v_m_s"]
    )
    assert data["propellant"] is None
    assert len(data["tradeoff"]) > 0
    assert len(data["samples"]) == 10
    assert data["samples"][-1]["t_s"] == pytest.approx(data["duration_s"])


def test_optimize_endpoint_computes_propellant_only_when_vehicle_defined(client, circular_ephemeris):
    response = client.post(
        "/transfers/optimize",
        json={
            "date": "2026-11-14T00:00:00Z",
            "max_duration_s": 6 * 86400,
            "parking_alt_m": 200_000,
            "samples": 5,
            "initial_mass_kg": 10000,
            "isp_s": 320,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["propellant"] is not None
    assert data["propellant"]["idealized"] is True
    assert 0 < data["propellant"]["propellant_mass_kg"] < 10000


def test_optimize_endpoint_returns_200_no_feasible_solution(client, circular_ephemeris):
    response = client.post(
        "/transfers/optimize",
        json={
            "date": "2026-11-14T00:00:00Z",
            "max_duration_s": 86400,
            "parking_alt_m": 200_000,
            "samples": 10,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "no_feasible_solution"
    assert len(data["reasons"]) > 0
    assert data["tradeoff"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"date": "2026-11-14T00:00:00", "max_duration_s": 864000},
        {"date": "2026-11-14T00:00:00Z", "max_duration_s": -100},
        {"date": "2026-11-14T00:00:00Z", "max_duration_s": 864000, "parking_alt_m": -10},
        {"date": "2026-11-14T00:00:00Z", "max_duration_s": 864000, "initial_mass_kg": 5000},
    ],
)
def test_optimize_endpoint_validation_returns_422(client, payload):
    response = client.post("/transfers/optimize", json=payload)
    assert response.status_code == 422


def test_optimize_endpoint_returns_502_on_horizons_error(client, monkeypatch):
    def broken_table(*args, **kwargs):
        raise EphemerisError("Horizons no disponible")

    monkeypatch.setattr("app.data.ephemeris.get_body_state_table", broken_table)
    response = client.post(
        "/transfers/optimize",
        json={"date": "2026-11-14T00:00:00Z", "max_duration_s": 10 * 86400},
    )
    assert response.status_code == 502


def test_legacy_transfers_endpoint_remains_available(client, circular_ephemeris):
    response = client.post(
        "/transfers",
        json={"date": "2026-11-14T00:00:00Z", "duration_s": 864000, "samples": 5},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["duration_s"] == 864000
    assert len(data["samples"]) == 5