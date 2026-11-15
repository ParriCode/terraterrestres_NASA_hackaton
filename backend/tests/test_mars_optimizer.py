"""Objetivo 2 (Marte): física del cribado y de la geometría de salida, sin red."""
import math
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from app.services.mars_optimizer import (
    arrival_periapsis_direction,
    build_tradeoff,
    departure_perigee_state,
    hyperbolic_delta_v,
    mars_sample_times,
    screen_lambert,
)

MU_SUN, MU_EARTH, MU_MARS = 1.3271244e20, 3.986004418e14, 4.282837e13
AU = 1.495978707e11


def test_hyperbolic_delta_v_matches_textbook_tmi():
    # v∞ = 2.94 km/s desde LEO de 200 km → TMI ≈ 3.6 km/s (Hohmann Tierra–Marte de manual).
    dv = hyperbolic_delta_v(2943.0, MU_EARTH, 6371e3 + 200e3)
    assert dv == pytest.approx(3.6e3, abs=60)


@pytest.mark.parametrize("v_inf", [2500.0, 3500.0, 6000.0])
def test_departure_hyperbola_leaves_along_v_infinity(v_inf):
    s = np.array([0.6, 0.7, 0.2]); s /= np.linalg.norm(s)
    r_park = 6571e3
    r_hat, v_hat, v_p = departure_perigee_state(s * v_inf, MU_EARTH, r_park, np.array([0.0, 0.0, 1.0]))
    assert abs(r_hat @ v_hat) < 1e-12
    # Propagación de dos cuerpos: la velocidad lejana debe apuntar a v̂∞ con módulo v∞.
    rhs = lambda t, y: np.concatenate((y[3:], -MU_EARTH * y[:3] / np.linalg.norm(y[:3]) ** 3))
    sol = solve_ivp(rhs, (0, 40 * 86400), np.concatenate((r_park * r_hat, v_p * v_hat)), rtol=1e-11, atol=1e-6)
    v_far = sol.y[3:, -1]
    assert np.degrees(np.arccos(v_far @ s / np.linalg.norm(v_far))) < 0.5
    assert np.linalg.norm(v_far) == pytest.approx(v_inf, rel=0.01)
    assert np.cross(r_hat, v_hat)[2] > 0  # prógrada respecto a +z


def test_arrival_periapsis_is_reached_from_minus_v_infinity():
    s = np.array([1.0, 0.0, 0.0]); r_p = 3389.5e3 + 300e3; v_inf = 3000.0
    rp_hat = arrival_periapsis_direction(s * v_inf, MU_MARS, r_p, np.array([0.0, 0.0, 1.0]))
    e = 1 + r_p * v_inf ** 2 / MU_MARS
    # Ángulo entre el periapsis y la dirección de procedencia (−v̂∞) = ν∞ = arccos(−1/e).
    assert math.degrees(math.acos(rp_hat @ -s)) == pytest.approx(math.degrees(math.acos(-1 / e)), abs=1e-9)


class _Body(SimpleNamespace):
    def pos(self, t):
        a = self.phase + self.n * t
        return (self.r * math.cos(a), self.r * math.sin(a), 0.0)

    def velocity(self, t):
        a = self.phase + self.n * t
        return (-self.r * self.n * math.sin(a), self.r * self.n * math.cos(a), 0.0)


def test_screening_recovers_hohmann_for_circular_coplanar_orbits():
    r_e, r_m = AU, 1.523679 * AU
    n_e, n_m = math.sqrt(MU_SUN / r_e ** 3), math.sqrt(MU_SUN / r_m ** 3)
    t_h = math.pi * math.sqrt(((r_e + r_m) / 2) ** 3 / MU_SUN)  # ≈ 258.9 días
    phase_m = math.pi - n_m * t_h - math.radians(0.5)  # Marte llega casi opuesto (evita 180° exactos)
    bodies = {
        "sun": _Body(r=0.0, n=0.0, phase=0.0, mu_m3_s2=MU_SUN, radius_m=6.957e8),
        "earth": _Body(r=r_e, n=n_e, phase=0.0, mu_m3_s2=MU_EARTH, radius_m=6371e3),
        "mars": _Body(r=r_m, n=n_m, phase=phase_m, mu_m3_s2=MU_MARS, radius_m=3389.5e3),
    }
    cands = screen_lambert(SimpleNamespace(bodies=bodies), 300 * 86400, step_s=86400)
    best = cands[0]
    assert abs(best.duration_s - t_h) < 4 * 86400
    assert best.v_inf_departure_m_s == pytest.approx(2.94e3, abs=150)
    assert best.v_inf_arrival_m_s == pytest.approx(2.65e3, abs=150)
    assert 5.5e3 < best.total_delta_v_m_s < 6.3e3
    curve = build_tradeoff(cands)
    assert [p.duration_s for p in curve] == sorted(p.duration_s for p in curve)


def test_mars_sample_times_dense_near_both_ends():
    T = 260 * 86400.0
    ts = mars_sample_times(T, 400)
    assert ts[0] == 0.0 and ts[-1] == T and np.all(np.diff(ts) > 0)
    assert 300 <= len(ts) <= 402
    # Escape de la Tierra y llegada a Marte con muchas muestras (antes: ~1 cada 0,65 días).
    assert np.sum(ts <= 2 * 86400) >= 60
    assert np.sum(ts >= T - 2 * 86400) >= 50
    assert np.array_equal(mars_sample_times(T, 20), np.linspace(0.0, T, 20))
