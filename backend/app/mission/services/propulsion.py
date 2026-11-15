"""Estimación idealizada de propelente (ecuación del cohete de Tsiolkovski)."""
import math
from dataclasses import dataclass

STANDARD_GRAVITY_M_S2 = 9.80665


@dataclass(frozen=True)
class PropellantEstimate:
    initial_mass_kg: float
    propellant_mass_kg: float
    final_mass_kg: float
    mass_fraction: float
    delta_v_m_s: float
    isp_s: float


def _validate_finite(value: float, name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValueError(f"{name} debe ser un número finito.")


def estimate_propellant_mass_kg(
    initial_mass_kg: float,
    delta_v_m_s: float,
    isp_s: float,
    *,
    g0_m_s2: float = STANDARD_GRAVITY_M_S2,
) -> float:
    """Estima m_prop = m0 * (1 - exp(-Δv / (Isp * g0))) con estabilidad numérica."""
    _validate_finite(initial_mass_kg, "initial_mass_kg")
    _validate_finite(delta_v_m_s, "delta_v_m_s")
    _validate_finite(isp_s, "isp_s")
    _validate_finite(g0_m_s2, "g0_m_s2")
    if initial_mass_kg <= 0:
        raise ValueError("initial_mass_kg debe ser positivo.")
    if delta_v_m_s < 0:
        raise ValueError("delta_v_m_s no puede ser negativo.")
    if isp_s <= 0:
        raise ValueError("isp_s debe ser positivo.")
    if g0_m_s2 <= 0:
        raise ValueError("g0_m_s2 debe ser positivo.")
    if delta_v_m_s == 0:
        return 0.0
    x = delta_v_m_s / (isp_s * g0_m_s2)
    return float(-initial_mass_kg * math.expm1(-x))


def estimate_propellant(
    initial_mass_kg: float,
    delta_v_m_s: float,
    isp_s: float,
    *,
    g0_m_s2: float = STANDARD_GRAVITY_M_S2,
) -> PropellantEstimate:
    """Devuelve el desglose completo de masa de propelente y masa final."""
    propellant_mass_kg = estimate_propellant_mass_kg(
        initial_mass_kg, delta_v_m_s, isp_s, g0_m_s2=g0_m_s2
    )
    final_mass_kg = float(initial_mass_kg - propellant_mass_kg)
    return PropellantEstimate(
        initial_mass_kg=float(initial_mass_kg),
        propellant_mass_kg=propellant_mass_kg,
        final_mass_kg=final_mass_kg,
        mass_fraction=float(propellant_mass_kg / initial_mass_kg),
        delta_v_m_s=float(delta_v_m_s),
        isp_s=float(isp_s),
    )