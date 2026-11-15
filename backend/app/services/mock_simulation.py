"""DATOS FICTICIOS para conectar React; no es un simulador gravitatorio.

La nave se mueve en línea recta con velocidad constante. Tierra y Luna
permanecen fijas; no hay RK2, gravedad ni detección de colisiones.
Los parámetros de demostración no sustituyen las efemérides verificadas.
"""

from __future__ import annotations

import math

from app.models.domain import (
    CelestialBody, Diagnostics, SimulationConfig, SimulationStatus,
    SpacecraftState, TrajectorySample, Vec3,
)
from app.services.simulation_service import (
    InvalidSimulationInputError, PropagationOutput, ScenarioContext,
    SimulationComponents, UnknownScenarioError, planned_steps,
)

MOCK_SCENARIO_ID = "mock_earth_moon_v1"
MOCK_WARNING = "FICTITIOUS_DATA_NO_ORBITAL_PHYSICS"


def load_mock_scenario(scenario_id: str) -> ScenarioContext:
    if scenario_id != MOCK_SCENARIO_ID:
        raise UnknownScenarioError(
            f"Escenario desconocido. En modo mock usa '{MOCK_SCENARIO_ID}'."
        )
    earth = CelestialBody(
        id="earth", name="Tierra (datos ficticios)",
        mu_m3_s2=4.0e14, radius_m=6.4e6,
    )
    moon = CelestialBody(
        id="moon", name="Luna (datos ficticios)",
        mu_m3_s2=5.0e12, radius_m=1.7e6,
    )
    separation_m = 3.8e8
    total_mu = earth.mu_m3_s2 + moon.mu_m3_s2
    earth_x = -separation_m * moon.mu_m3_s2 / total_mu
    moon_x = separation_m * earth.mu_m3_s2 / total_mu

    def positions_at(t_s: float) -> dict[str, Vec3]:
        # Copia nueva por muestra: los cuerpos están fijos SOLO en el mock.
        return {"earth": (earth_x, 0.0, 0.0), "moon": (moon_x, 0.0, 0.0)}

    return ScenarioContext(scenario_id, [earth, moon], positions_at)


def _finite_distances(position: Vec3, body_positions: dict[str, Vec3]) -> bool:
    return all(math.isfinite(math.dist(position, pos)) for pos in body_positions.values())


def propagate_mock(config: SimulationConfig, scenario: ScenarioContext) -> PropagationOutput:
    initial_positions = scenario.positions_at(0.0)
    if not _finite_distances(config.initial_state.position_m, initial_positions):
        raise InvalidSimulationInputError(
            "El estado inicial produce distancias fuera del rango numérico representable."
        )
    samples = [TrajectorySample(0.0, config.initial_state, initial_positions)]
    status = SimulationStatus.COMPLETED
    for index in range(1, planned_steps(config) + 1):
        t_s = min(index * config.step_s, config.duration_s)
        position: Vec3 = tuple(
            p + v * t_s
            for p, v in zip(config.initial_state.position_m, config.initial_state.velocity_m_s)
        )
        body_positions = scenario.positions_at(t_s)
        if not all(math.isfinite(v) for v in position) or not _finite_distances(position, body_positions):
            status = SimulationStatus.NUMERICAL_ERROR
            break  # Conservamos únicamente las muestras anteriores válidas.
        samples.append(TrajectorySample(
            t_s, SpacecraftState(position, config.initial_state.velocity_m_s), body_positions,
        ))
        if t_s == config.duration_s:
            break
    return PropagationOutput(status=status, samples=samples, events=[])


def diagnose_mock(
    samples: list[TrajectorySample], bodies: list[CelestialBody]
) -> Diagnostics:
    """Diagnóstico de los estados sintéticos de demostración."""
    distances = {
        body.id: min(
            math.dist(sample.spacecraft.position_m, sample.body_positions_m[body.id])
            for sample in samples
        )
        for body in bodies
    }
    return Diagnostics(
        final_time_s=samples[-1].t_s,
        steps_completed=len(samples) - 1,
        min_distance_m=distances,
        min_altitude_m={body.id: distances[body.id] - body.radius_m for body in bodies},
    )


def build_mock_components() -> SimulationComponents:
    return SimulationComponents(load_mock_scenario, propagate_mock, diagnose_mock)