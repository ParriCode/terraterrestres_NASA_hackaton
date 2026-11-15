"""Objetivo 3 (Marte): API sin red. La Luna conserva sus valores por defecto y límites."""
from fastapi.testclient import TestClient
import pytest

import app.controllers.mission_controller as mc
from app.main import create_app
from app.services.mars_optimizer import MarsTradeoffPoint, NoFeasibleMarsTransfer

client = TestClient(create_app())
DATE = "2026-11-15T00:00:00Z"


def test_request_defaults_to_moon():
    req = mc.OptimizeTransferRequest(date=DATE)
    assert req.destination == "moon" and req.max_duration_s == 10 * 86400


@pytest.mark.parametrize("payload", [
    {"max_duration_s": 31 * 86400},                          # Luna: sigue limitada a 30 días
    {"destination": "mars", "max_duration_s": 100 * 86400},  # Marte: mínimo 120 días
    {"destination": "mars", "max_duration_s": 401 * 86400},  # Marte: máximo 400 días
    {"destination": "jupiter"},
])
def test_invalid_requests_rejected_before_any_computation(payload, monkeypatch):
    monkeypatch.setattr(mc, "optimize_transfer", lambda *a, **k: pytest.fail("no debe calcular"))
    monkeypatch.setattr(mc, "optimize_mars_transfer", lambda *a, **k: pytest.fail("no debe calcular"))
    assert client.post("/missions/optimize", json={"date": DATE, **payload}).status_code == 422


def test_moon_request_never_reaches_mars_engine(monkeypatch):
    called = {}
    monkeypatch.setattr(mc, "optimize_mars_transfer", lambda *a, **k: pytest.fail("Luna no debe ir a Marte"))

    def fake_moon(*args, **kwargs):
        called["moon"] = True
        raise mc.NoFeasibleTransfer(["sin candidatos"], max_duration_s=args[1])

    monkeypatch.setattr(mc, "optimize_transfer", fake_moon)
    r = client.post("/missions/optimize", json={"date": DATE})
    assert r.status_code == 200 and called["moon"] and "destination" not in r.json()


@pytest.mark.parametrize("path, extra", [("/missions/optimize", {"destination": "mars"}), ("/missions/mars", {})])
def test_mars_no_feasible_is_structured(path, extra, monkeypatch):
    def fake(*args, **kwargs):
        raise NoFeasibleMarsTransfer(["el disparo no convergió"], [MarsTradeoffPoint(200 * 86400.0, 3700.0, 2400.0, 6100.0)],
                                     max_duration_s=args[1])

    monkeypatch.setattr(mc, "optimize_mars_transfer", fake)
    r = client.post(path, json={"date": DATE, "max_duration_s": 260 * 86400, **extra})
    body = r.json()
    assert r.status_code == 200, body
    assert body["status"] == "no_feasible_solution" and body["destination"] == "mars"
    assert body["tradeoff"][0]["estimated_total_delta_v_m_s"] == 6100.0
