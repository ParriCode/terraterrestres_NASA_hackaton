"""Pruebas unitarias para la estimación idealizada de propelente."""
import math

import pytest

from app.services.propulsion import (
    STANDARD_GRAVITY_M_S2,
    estimate_propellant,
    estimate_propellant_mass_kg,
)


def test_zero_delta_v_requires_zero_propellant():
    assert estimate_propellant_mass_kg(1000.0, 0.0, 320.0) == 0.0
    est = estimate_propellant(1000.0, 0.0, 320.0)
    assert est.propellant_mass_kg == 0.0
    assert est.final_mass_kg == 1000.0
    assert est.mass_fraction == 0.0


def test_positive_delta_v_and_higher_isp_reduces_propellant():
    m_low_isp = estimate_propellant_mass_kg(5000.0, 4000.0, 300.0)
    m_high_isp = estimate_propellant_mass_kg(5000.0, 4000.0, 450.0)
    assert 0.0 < m_high_isp < m_low_isp < 5000.0


def test_small_delta_v_numerical_stability():
    m0 = 1000.0
    dv = 1e-11
    isp = 300.0
    m_prop = estimate_propellant_mass_kg(m0, dv, isp)
    expected_linear = m0 * dv / (isp * STANDARD_GRAVITY_M_S2)
    assert m_prop > 0.0
    assert m_prop == pytest.approx(expected_linear, rel=1e-9)


@pytest.mark.parametrize(
    "m0,dv,isp",
    [
        (0.0, 1000.0, 300.0),
        (-500.0, 1000.0, 300.0),
        (1000.0, -1.0, 300.0),
        (1000.0, 1000.0, 0.0),
        (1000.0, 1000.0, -300.0),
        (math.nan, 1000.0, 300.0),
        (1000.0, math.inf, 300.0),
        (1000.0, 1000.0, math.nan),
    ],
)
def test_invalid_propulsion_inputs_raise_value_error(m0, dv, isp):
    with pytest.raises(ValueError):
        estimate_propellant_mass_kg(m0, dv, isp)