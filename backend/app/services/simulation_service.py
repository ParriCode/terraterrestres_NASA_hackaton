"""Coordinación de simulación: escenario -> propagación -> diagnóstico -> resultado.

ScenarioContext y PropagationOutput son interfaces locales para los adaptadores.
No requieren modificar los modelos compartidos ni los proveedores de datos.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math

from app.models.domain import (
    CelestialBody, Diagnostics, Event, SimulationConfig, SimulationResult,
    SimulationStatus, TrajectorySample, Vec3,
)

MAX_STEPS = 10_000  # Límite operativo para esta API síncrona de desarrollo.


class SimulationServiceError(Exception):
    """Fallo esperado que el controlador traduce a un error HTTP."""


class UnknownScenarioError(SimulationServiceError):
    pass


class SimulationLimitError(SimulationServiceError):
    pass


class SimulationNotReadyError(SimulationServiceError):
    pass


class InvalidSimulationInputError(SimulationServiceError):
    pass


@dataclass(frozen=True)
class ScenarioContext:
    """Adaptador de propiedades y posiciones para un mismo escenario."""

    scenario_id: str
    bodies: list[CelestialBody]
    positions_at: Callable[[float], dict[str, Vec3]]


@dataclass(frozen=True)
class PropagationOutput:
    """Trayectoria y eventos antes del diagnóstico."""

    status: SimulationStatus
    samples: list[TrajectorySample]
    events: list[Event]


@dataclass(frozen=True)
class SimulationComponents:
    """Dependencias para cargar escenarios, propagar y diagnosticar."""

    load_scenario: Callable[[str], ScenarioContext]
    propagate: Callable[[SimulationConfig, ScenarioContext], PropagationOutput]
    diagnose: Callable[[list[TrajectorySample], list[CelestialBody]], Diagnostics]


SimulationRunner = Callable[[SimulationConfig], SimulationResult]


def planned_steps(config: SimulationConfig) -> int:
    """Limita el trabajo antes de asignar memoria; admite un último paso corto."""
    ratio = config.duration_s / config.step_s
    if not math.isfinite(ratio) or ratio > MAX_STEPS:
        raise SimulationLimitError(
            f"La petición supera el límite de {MAX_STEPS} pasos. "
            "Reduce duration_s o aumenta step_s."
        )
    return max(1, math.ceil(ratio))


def run_simulation(
    config: SimulationConfig,
    *,
    components: SimulationComponents | None = None,
) -> SimulationResult:
    """Ejecuta el flujo común. Sin componentes reales devuelve un fallo explícito.

    main.py fija components con functools.partial para exponer a los
    controladores una función que recibe únicamente config.
    """
    planned_steps(config)
    if components is None:
        raise SimulationNotReadyError(
            "El motor real aún no está conectado. Faltan los adaptadores "
            "de escenarios, propagación y diagnóstico."
        )

    # 1. Obtener cuerpos y proveedor de posiciones.
    scenario = components.load_scenario(config.scenario_id)
    if scenario.scenario_id != config.scenario_id:
        raise RuntimeError("El proveedor devolvió un escenario distinto del solicitado.")

    # 2. Propagar el estado y detectar los eventos.
    propagation = components.propagate(config, scenario)

    # 3. Resumir la trayectoria realmente obtenida.
    diagnostics = components.diagnose(propagation.samples, scenario.bodies)

    # 4. Conservar la configuración y construir la respuesta compartida.
    return SimulationResult(
        config=config,
        bodies=scenario.bodies,
        status=propagation.status,
        samples=propagation.samples,
        events=propagation.events,
        diagnostics=diagnostics,
    )
