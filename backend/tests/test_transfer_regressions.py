"""Regresiones de contratos, CORS y gravedad indirecta sin JPL ni red."""

from types import SimpleNamespace

import numpy as np
from fastapi.testclient import TestClient

from app.main import create_app
from app.physics.dynamics import state_derivative_array
from app.services.mission_optimizer import NoFeasibleTransfer
from app.controllers.transfer_controller import _serialize_samples


def test_routes_registered_with_json_schema_and_default_cors(monkeypatch):
    monkeypatch.delenv("ORBITAL_CORS_ORIGINS", raising=False)
    app = create_app()
    client = TestClient(app)
    paths = app.openapi()["paths"]
    assert all(path in paths and "post" in paths[path] for path in (
        "/transfers", "/transfers/optimize", "/transfers/round-trip"
    ))
    # Incluso con ORBITAL_SIMULATION_MODE=mock, los tres endpoints de
    # transferencias siempre ejecutan el motor físico real.
    bad = client.post("/transfers/optimize", json={"date": "sin fecha"})
    assert bad.status_code == 422
    assert bad.headers["x-simulation-mode"] == "real"
    for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
        preflight = client.options(
            "/transfers/round-trip",
            headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == origin


def test_roundtrip_no_feasible_json_contract(monkeypatch):
    def fail_solver(*args, **kwargs):
        raise NoFeasibleTransfer(["Sin geometría viable en esta ventana."])

    monkeypatch.setattr("app.controllers.transfer_controller.optimize_round_trip_transfer", fail_solver)
    resp = TestClient(create_app()).post(
        "/transfers/round-trip",
        json={"date": "2026-11-15T00:00:00Z", "mode": "free_return", "max_total_duration_s": 1209600},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "no_feasible_solution"
    assert data["max_total_duration_s"] == 1209600
    assert data["reasons"] == ["Sin geometría viable en esta ventana."]


def test_ephemeris_error_is_structured(monkeypatch):
    from app.data.ephemeris import EphemerisError

    def fail(*args, **kwargs):
        raise EphemerisError("Servicio remoto no disponible")

    monkeypatch.setattr("app.controllers.transfer_controller.optimize_transfer", fail)
    resp = TestClient(create_app()).post(
        "/transfers/optimize",
        json={"date": "2026-11-15T00:00:00Z", "max_duration_s": 864000},
    )
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "ephemeris_unavailable"


def test_sun_indirect_term_cancels_uniform_acceleration_at_barycenter():
    solar_mu = 1.3271244004193938e20
    solar_distance = 1.5e11
    sun = SimpleNamespace(id="sun", mu_m3_s2=solar_mu, pos=lambda t: (solar_distance, 0.0, 0.0))
    origin = state_derivative_array(0.0, np.zeros(6), (sun,))
    assert np.linalg.norm(origin[3:]) < 1e-14

    pos_x = 1e7
    y = np.array((pos_x, 0., 0., 0., 0., 0.))
    tide = state_derivative_array(0.0, y, (sun,))[3]
    expected = solar_mu / (solar_distance - pos_x) ** 2 - solar_mu / solar_distance**2
    np.testing.assert_allclose(tide, expected, rtol=1e-8)


def test_vectorized_samples_include_sun_and_preserve_timestamps():
    class Dense:
        def sol(self, ts):
            ts = np.asarray(ts)
            return np.array((ts * 2., ts * 3., ts * 0., ts * 0. + 2., ts * 0. + 3., ts * 0.))

    class Motion:
        def __call__(self, ts):
            ts = np.asarray(ts)
            return np.column_stack((ts, ts * 0., ts * 0.))

    bodies = {
        key: SimpleNamespace(_motion=Motion()) for key in ("earth", "moon", "sun")
    }
    fake = SimpleNamespace(
        scenario=SimpleNamespace(bodies=bodies),
        _segments=((0., 10., Dense()),),
    )
    points = _serialize_samples(fake, 10., 5)
    assert len(points) == 5
    assert points[-1]["t_s"] == 10.
    assert points[-1]["velocity_m_s"] == [2., 3., 0.]
    assert points[-1]["body_positions_m"]["sun"] == [10., 0., 0.]


def test_roundtrip_time_grid_preserves_impulsive_burns():
    from app.controllers.transfer_controller import _time_grid

    fake = SimpleNamespace(_segments=(
        (0., 2000., object()), (2000., 3000., object()), (3000., 5000., object()),
    ))
    ts = _time_grid(fake, 5000., 100)
    assert len(ts) == 100
    assert ts[0] == 0. and ts[-1] == 5000.
    assert np.all(np.diff(ts) > 0)
    assert 2000. in ts and 3000. in ts
    assert any(0 < 2000. - t <= 0.051 for t in ts)
    assert any(0 < 3000. - t <= 0.051 for t in ts)


def test_3d_propagation_stops_at_planet_impact():
    from app.services.mission_optimizer import _propagate_3d

    body = SimpleNamespace(
        id="earth", mu_m3_s2=1e-9, radius_m=1.0,
        pos=lambda t: (0.0, 0.0, 0.0),
    )
    y0 = np.array((-2.0, 0., 0., 4.0, 0., 0.))
    result = _propagate_3d((body,), y0, 0.0, 1.0)
    assert not result.success
    assert result.t[-1] < 1.0
    assert "impactó" in result.message
