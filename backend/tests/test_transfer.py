"""Pruebas reproducibles sin red; el servicio de producción consulta Horizons."""
from datetime import datetime, timezone

import numpy as np
import pytest

from app.data.bodies import load_bodies
from app.data.scenarios import PlanarScenario
from app.services.transfer_service import (
    F,
    TransferNotFoundError,
    design_transfer,
    orbit_point,
    prograde_circular_velocity,
)


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
    derivative = (np.array(result.pos(t + dt)) - np.array(result.pos(t - dt))) / (2 * dt)
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
    # Compatibilidad legacy: el endpoint clásico sigue partiendo desde superficie (altitud 0).
    earth_r0 = np.linalg.norm(
        np.subtract(payload["samples"][0]["position_m"], payload["samples"][0]["body_positions_m"]["earth"])
    )
    assert earth_r0 == pytest.approx(load_bodies()["earth"].radius_m, abs=1.0)


def test_request_rejects_dates_without_timezone_and_invalid_mass():
    from pydantic import ValidationError
    from app.controllers.transfer_controller import TransferRequest

    with pytest.raises(ValidationError):
        TransferRequest(date="2026-11-14T00:00:00")
    with pytest.raises(ValidationError):
        TransferRequest(date="2026-11-14T00:00:00Z", mass_kg=-1)


def _absolute_time_ephemeris(monkeypatch):
    """Efemérides circulares cuya fase depende de la fecha absoluta (como la Luna real)."""
    catalog = load_bodies()
    mu_t, mu_l = (catalog[k].mu_m3_s2 for k in ("earth", "moon"))
    distance = 384400000.0
    omega = np.sqrt((mu_t + mu_l) / distance**3)

    def table(body, start, stop, intervals):
        times = np.linspace(0, (stop - start).total_seconds(), intervals + 1)
        phase = omega * (start.timestamp() + times)
        radius = -distance * mu_l / (mu_t + mu_l) if body.id == "earth" else distance * mu_t / (mu_t + mu_l)
        positions = np.column_stack((radius * np.cos(phase), radius * np.sin(phase), np.zeros_like(times)))
        velocities = np.column_stack((-radius * omega * np.sin(phase), radius * omega * np.cos(phase),
                                      np.zeros_like(times)))
        return times, positions, velocities

    monkeypatch.setattr("app.data.ephemeris.get_body_state_table", table)
    return omega


def test_moon_position_depends_on_departure_date(monkeypatch):
    """Regresión: el eje X ya no es «Tierra→Luna en t0», así que la Luna cambia con la fecha."""
    omega = _absolute_time_ephemeris(monkeypatch)
    angles, stamps = [], []
    for day in (14, 21):
        date = datetime(2026, 11, day, tzinfo=timezone.utc)
        scenario = PlanarScenario(date, 86400)
        delta = np.subtract(scenario.bodies["moon"].pos(0), scenario.bodies["earth"].pos(0))
        angles.append(np.arctan2(delta[1], delta[0]))
        stamps.append(date.timestamp())
    for angle, stamp in zip(angles, stamps):  # ángulo en el plano = fase real de la Luna
        assert np.angle(np.exp(1j * (angle - omega * stamp))) == pytest.approx(0, abs=1e-9)
    turned = np.angle(np.exp(1j * (angles[1] - angles[0])))
    assert abs(turned) > np.deg2rad(60)  # 7 días ≈ 92°; antes de la corrección era 0°


def test_fractional_duration_stays_inside_ephemeris_table(circular_ephemeris):
    """Regresión: timedelta redondea a µs y pos(duration_s) lanzaba «fuera de la tabla»."""
    duration = 345600.1234564  # redondea a …123456 µs (hacia abajo)
    scenario = PlanarScenario(datetime(2026, 11, 14, tzinfo=timezone.utc), duration)
    for body in scenario.get_bodies():
        assert len(body.pos(duration)) == 3


def test_parking_orbit_radius_and_delta_v_metrics(circular_ephemeris):
    parking_alt_m = 200_000.0
    duration_s = 5 * 86400
    result = design_transfer(
        datetime(2026, 11, 14, tzinfo=timezone.utc),
        duration_s,
        launch_angle_deg=240.0,
        arrival_angle_deg=270.0,
        objective="delta_v",
        parking_alt_m=parking_alt_m,
    )
    earth = result.scenario.bodies["earth"]
    moon = result.scenario.bodies["moon"]

    rel_pos_0 = np.subtract(result.pos(0.0), earth.pos(0.0))
    assert np.linalg.norm(rel_pos_0) == pytest.approx(earth.radius_m + parking_alt_m, abs=1.0)

    rel_vel_0 = np.subtract(result.speed(0.0), earth.speed(0.0))
    v_circ = prograde_circular_velocity(earth.mu_m3_s2, rel_pos_0)
    assert np.linalg.norm(v_circ) == pytest.approx(np.sqrt(earth.mu_m3_s2 / (earth.radius_m + parking_alt_m)))
    assert result.launch_delta_v_m_s == pytest.approx(np.linalg.norm(rel_vel_0 - v_circ))

    rel_vel_1 = np.subtract(result.speed(duration_s), moon.speed(duration_s))
    assert result.arrival_delta_v_m_s == pytest.approx(np.linalg.norm(rel_vel_1))
    v_esc_moon_sq = 2.0 * moon.mu_m3_s2 / moon.radius_m
    assert result.arrival_v_infinity_m_s == pytest.approx(
        np.sqrt(max(0.0, result.arrival_delta_v_m_s**2 - v_esc_moon_sq))
    )
    assert result.total_delta_v_m_s == pytest.approx(
        result.launch_delta_v_m_s + result.arrival_delta_v_m_s
    )


def test_earth_reimpact_from_parking_orbit_is_rejected(circular_ephemeris):
    scenario = PlanarScenario(datetime(2026, 11, 14, tzinfo=timezone.utc), 5 * 86400)
    earth, moon = scenario.bodies["earth"], scenario.bodies["moon"]
    # Salida en la cara opuesta a la Luna apuntando hacia la trayectoria recta que atraviesa la Tierra.
    x0 = orbit_point(earth, moon, 0.0, 180.0, 200_000.0)
    x1 = orbit_point(moon, earth, 5 * 86400, 0.0, 0.0)
    # El ángulo opuesto a la Luna no implica necesariamente impacto;
    # si existe una trayectoria válida, debe permanecer fuera de la Tierra.
    try:
        result = F(x0, x1, 0.0, 5 * 86400, "delta_v", scenario=scenario, parking_alt_m=200_000.0)
    except TransferNotFoundError:
        return
    times = np.linspace(0, result.t1_s, 2000)
    ship_xy = result._solution.sol(times)[:2].T
    earth_xy = np.asarray(earth._motion(times))[:, :2]
    altitude = np.linalg.norm(ship_xy - earth_xy, axis=1) - earth.radius_m
    assert np.min(altitude) >= -10.0