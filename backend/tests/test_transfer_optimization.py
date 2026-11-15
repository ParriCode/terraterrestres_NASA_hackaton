"""Pruebas offline: optimización angular y contrato FastAPI."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.services.transfer_service as service
from app.controllers.transfer_controller import OptimizeTransferRequest, optimize
from app.main import create_app


def test_optimizer_chooses_different_angles_for_different_objectives(monkeypatch):
    """No confunde mínimo de energía con mínimo de distancia."""
    constructed = []

    class Body:
        radius_m = 1.0

        def __init__(self, pos):
            self.xyz = pos

        def pos(self, time):
            return self.xyz

    class Scenario:
        def __init__(self, date, duration_s, *, spacing_s):
            constructed.append(self)
            self.bodies = {"earth": Body((0., 0., 0.)), "moon": Body((100., 0., 0.))}

    fake_results = []

    def fake_F(start, target, t0, t1, goal, **kwargs):
        # Coordenadas del punto de llegada respecto al vector Luna->Tierra.
        # -90 grados: y=+1. +90 grados: y=-1.
        rel = target[1]
        fake_results.append((start, target, kwargs["scenario"]))
        return SimpleNamespace(
            launch_energy_j=100.0 + (rel + 1.0)**2 * 100,
            path_length_m=100.0 + (rel - 1.0)**2 * 100,
        )

    monkeypatch.setattr(service, "PlanarScenario", Scenario)
    monkeypatch.setattr(service, "F", fake_F)

    date = datetime(2026, 11, 14, tzinfo=timezone.utc)
    energy = service.optimize_transfer(date, 86400, objective="energia", coarse_step_deg=90)
    distance = service.optimize_transfer(date, 86400, objective="distancia", coarse_step_deg=90)
    assert energy.arrival_angle_deg == 90.0
    assert distance.arrival_angle_deg == -90.0
    assert len(constructed) == 2  # no descarga extra por ángulo
    assert all(row[2] is constructed[0] for row in fake_results[:6])
    assert energy.search_complete and distance.search_complete
    assert energy.valid_candidates > 0


def test_optimizer_reports_no_valid_candidate(monkeypatch):
    class Scenario:
        def __init__(self, date, duration_s, *, spacing_s):
            self.bodies = {"earth": SimpleNamespace(pos=lambda t: (0., 0., 0.), radius_m=1.0),
                           "moon": SimpleNamespace(pos=lambda t: (10., 0., 0.), radius_m=1.0)}

    monkeypatch.setattr(service, "PlanarScenario", Scenario)

    def invalid(*a, **k):
        raise service.TransferNotFoundError("Sin solución")

    monkeypatch.setattr(service, "F", invalid)
    with pytest.raises(service.TransferNotFoundError, match="No se encontró una transferencia"):
        service.optimize_transfer(datetime.now(timezone.utc), 86400, coarse_step_deg=90)


def test_endpoint_contract_and_mode_header(monkeypatch):
    class FakeBody:
        name = 'Tierra'
        radius_m = 6371000.

        def pos(self, t):
            return (1.0, 2.0, 0.0)

    fake = SimpleNamespace(
        scenario=SimpleNamespace(basis_icrf=SimpleNamespace(tolist=lambda: [[1., 0., 0.], [0., 1., 0.]]),
                                 bodies={"earth": FakeBody(), "moon": FakeBody()}),
        objective="energia", mass_kg=1000., initial_velocity_m_s=(1., 2., 0.),
        launch_speed_m_s=3., launch_energy_j=4500., path_length_m=20., arrival_error_m=0.5,
        pos=lambda t: (t, 0., 0.), speed=lambda t: (1., 0., 0.),
    )

    monkeypatch.setattr('app.controllers.transfer_controller.optimize_transfer',
                        lambda *a, **kw: SimpleNamespace(transfer=fake, arrival_angle_deg=-45.,
                                                        attempted_angles_deg=(-90., -45., 0.),
                                                        valid_candidates=2, search_complete=True,
                                                        timed_out_angles_deg=()))
    client = TestClient(create_app(simulation_mode="mock"))
    response = client.post('/transfers/optimize', json={
        "date": "2026-11-14T00:00:00Z", "duration_s": 86400,
        "mass_kg": 1000, "objective": "energia", "samples": 3,
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['arrival_angle_deg'] == -45.0
    assert data['samples'][-1]['t_s'] == 86400
    assert data['optimization']['global_optimum_guaranteed'] is False
    assert response.headers['X-Simulation-Mode'] == 'real'


def test_optimize_rejects_invalid_request():
    with pytest.raises(ValidationError):
        OptimizeTransferRequest(date="2026-11-14T00:00:00", duration_s=10)
    with pytest.raises(ValidationError):
        OptimizeTransferRequest(date="2026-11-14T00:00:00Z", duration_s=40 * 86400)
    with pytest.raises(ValidationError):
        OptimizeTransferRequest(date="2026-11-14T00:00:00Z", mass_kg=0)
