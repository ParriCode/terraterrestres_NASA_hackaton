"""Pruebas reproducibles sin red; el servicio de producción consulta Horizons."""
from datetime import datetime, timezone

import numpy as np
import pytest

from app.data.bodies import load_bodies
from app.data.scenarios import PlanarScenario
from app.services.transfer_service import F, design_transfer


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


def test_full_transfer_dense_state_and_energy(circular_ephemeris):
    result = design_transfer(datetime(2026, 11, 14, tzinfo=timezone.utc), 10 * 86400)
    assert result.arrival_error_m < 1000
    assert result.launch_energy_j == pytest.approx(0.5 * result.mass_kg * result.launch_speed_m_s**2)
    assert result.path_length_m > 300000000
    assert result.pos(0)[2] == 0
    assert result.speed(432000)[2] == 0
    assert np.linalg.norm(result.speed(0)) > 10000
    # La derivada de C(t) debe coincidir con la velocidad que se expone.
    t, dt = 432000, 0.1
    derivative = (np.array(result.pos(t + dt)) - result.pos(t - dt)) / (2 * dt)
    assert derivative == pytest.approx(result.speed(t), abs=1e-3)
    energies = result.energy(t)
    assert energies["mechanical_j"] == pytest.approx(energies["kinetic_j"] + energies["potential_j"])
    with pytest.raises(ValueError):
        result.pos(-1)


def test_projection_preserves_initial_separation(circular_ephemeris):
    scenario = PlanarScenario(datetime(2026, 11, 14, tzinfo=timezone.utc), 86400)
    delta = np.subtract(scenario.bodies["moon"].pos(0), scenario.bodies["earth"].pos(0))
    assert delta == pytest.approx((384400000, 0, 0))
    with pytest.raises(ValueError):
        F((0., 0., 1.), (1., 1., 0.), 0, 86400, scenario=scenario)


def test_controller_exposes_transfer_samples(circular_ephemeris):
    import json
    from fastapi.encoders import jsonable_encoder
    from app.controllers.transfer_controller import TransferRequest, transfer

    request = TransferRequest(date="2026-11-14T00:00:00Z", duration_s=864000, samples=5)
    payload = json.loads(json.dumps(jsonable_encoder(transfer(request)), allow_nan=False))
    assert len(payload["samples"]) == 5
    assert payload["arrival_error_m"] < 1000
    assert payload["samples"][-1]["t_s"] == 864000
    assert payload["samples"][0]["velocity_m_s"] == pytest.approx(payload["initial_velocity_m_s"])
    assert payload["bodies"]["earth"]["radius_m"] == load_bodies()["earth"].radius_m
    assert payload["bodies"]["moon"]["radius_m"] == load_bodies()["moon"].radius_m


def test_request_rejects_dates_without_timezone_and_invalid_mass():
    from pydantic import ValidationError
    from app.controllers.transfer_controller import TransferRequest

    with pytest.raises(ValidationError):
        TransferRequest(date="2026-11-14T00:00:00")
    with pytest.raises(ValidationError):
        TransferRequest(date="2026-11-14T00:00:00Z", mass_kg=-1)
