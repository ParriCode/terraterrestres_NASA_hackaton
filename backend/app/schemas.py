"""Contrato JSON v1 de ORBITAL 4B para FastAPI (Python 3.10+, Pydantic 2).

Los modelos con sufijo Schema representan la API. Las clases del dominio y
sus validaciones físicas pertenecen a app.models.domain.

Uso en el controlador:
    request: SimulationRequest
    config = request.to_domain()
    result = run_simulation(config)
    response = SimulationResponse.from_domain(result)

FastAPI serializa estos modelos directamente. Para obtener un diccionario
con listas JSON en lugar de tuplas, usa response.model_dump(mode="json").
Este módulo se puede importar sin domain.py; to_domain() lo necesita cuando
se invoque. No comprueba el registro de escenarios ni calcula física.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

if TYPE_CHECKING:
    from .models.domain import SimulationConfig as DomainSimulationConfig
    from .models.domain import SimulationResult as DomainSimulationResult


# Los enteros JSON también son números válidos; bool y cadenas no lo son.
FiniteNumber = Annotated[float, Field(strict=True, allow_inf_nan=False)]
PositiveNumber = Annotated[FiniteNumber, Field(gt=0)]
NonNegativeNumber = Annotated[FiniteNumber, Field(ge=0)]
Vec3 = tuple[FiniteNumber, FiniteNumber, FiniteNumber]
BodyId = Literal["earth", "moon"]

_BODY_IDS = frozenset({"earth", "moon"})
_UNITS = {
    "length": "m",
    "time": "s",
    "velocity": "m/s",
    "gravitational_parameter": "m^3/s^2",
}


def _enum_value(value: object) -> object:
    """Acepta también las enumeraciones de domain.py al preparar la respuesta."""
    return value.value if isinstance(value, Enum) else value


EventType = Annotated[Literal["collision"], BeforeValidator(_enum_value)]
SimulationStatus = Annotated[
    Literal["completed", "collision", "numerical_error"],
    BeforeValidator(_enum_value),
]


def _check_body_ids(keys: Iterable[str]) -> None:
    if set(keys) != _BODY_IDS:
        raise ValueError("El contrato v1 requiere exactamente earth y moon.")


class _Schema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        validate_default=True,
    )


class CelestialBodySchema(_Schema):
    """Propiedades constantes; las posiciones van en cada muestra."""

    id: BodyId
    name: str = Field(min_length=1)
    mu_m3_s2: PositiveNumber
    radius_m: PositiveNumber

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name no puede estar vacío.")
        return value


class SpacecraftStateSchema(_Schema):
    """Estado respecto al baricentro, sin duplicar el tiempo de la muestra."""

    position_m: Vec3
    velocity_m_s: Vec3


class SimulationConfigSchema(_Schema):
    """Cuerpo de POST /simulations. El integrador v1 es RK2 del punto medio."""

    scenario_id: str = Field(min_length=1)
    initial_state: SpacecraftStateSchema
    duration_s: PositiveNumber
    step_s: PositiveNumber
    date: datetime

    @field_validator("date", mode="before")
    @classmethod
    def date_input_type(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError("date debe ser una fecha ISO 8601 con zona horaria.")
        return value

    @field_validator("date")
    @classmethod
    def date_in_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("date debe incluir zona horaria, por ejemplo Z o +01:00.")
        return value.astimezone(timezone.utc)

    @field_validator("scenario_id")
    @classmethod
    def scenario_id_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("scenario_id no puede estar vacío.")
        # El servicio comprueba su existencia en el registro de escenarios.
        return value

    def to_domain(self) -> DomainSimulationConfig:
        """Construye los objetos de dominio sin modificar la petición recibida."""
        from .models.domain import SimulationConfig, SpacecraftState

        return SimulationConfig(
            scenario_id=self.scenario_id,
            initial_state=SpacecraftState(
                position_m=self.initial_state.position_m,
                velocity_m_s=self.initial_state.velocity_m_s,
            ),
            duration_s=self.duration_s,
            step_s=self.step_s,
            date=self.date,
        )

    # step_s puede superar duration_s: el motor acorta el último paso.


class TrajectorySampleSchema(_Schema):
    """Nave y cuerpos en el mismo instante t_s."""

    t_s: NonNegativeNumber
    spacecraft: SpacecraftStateSchema
    body_positions_m: dict[BodyId, Vec3]

    @field_validator("body_positions_m")
    @classmethod
    def all_body_positions(cls, value: dict[BodyId, Vec3]) -> dict[BodyId, Vec3]:
        _check_body_ids(value)
        return value


class EventSchema(_Schema):
    """Evento calculado por ORBITAL4B. En v1 solo existe collision."""

    type: EventType
    t_s: NonNegativeNumber
    body_id: BodyId
    position_m: Vec3


class DiagnosticsSchema(_Schema):
    """Los mínimos del resumen se estiman sobre las muestras guardadas."""

    final_time_s: NonNegativeNumber
    steps_completed: int = Field(strict=True, ge=0)
    min_distance_m: dict[BodyId, NonNegativeNumber]
    # Una altitud negativa es válida si una muestra queda dentro de un cuerpo.
    min_altitude_m: dict[BodyId, FiniteNumber]

    @field_validator("min_distance_m", "min_altitude_m")
    @classmethod
    def all_body_diagnostics(cls, value: dict[BodyId, float]) -> dict[BodyId, float]:
        _check_body_ids(value)
        return value


class SimulationResultSchema(_Schema):
    """Respuesta completa, incluida una trayectoria parcial si falla el cálculo."""

    schema_version: Literal["1.0"] = "1.0"
    config: SimulationConfigSchema
    frame: Literal["earth_moon_barycentric_inertial"] = (
        "earth_moon_barycentric_inertial"
    )
    units: dict[str, str] = Field(
        default_factory=lambda: dict(_UNITS),
        json_schema_extra={"const": dict(_UNITS)},
    )
    bodies: list[CelestialBodySchema] = Field(min_length=2, max_length=2)
    status: SimulationStatus
    samples: list[TrajectorySampleSchema] = Field(min_length=1)
    events: list[EventSchema]
    diagnostics: DiagnosticsSchema

    @field_validator("units")
    @classmethod
    def fixed_units(cls, value: dict[str, str]) -> dict[str, str]:
        if value != _UNITS:
            raise ValueError("units debe coincidir con las unidades SI del contrato v1.")
        return value

    @field_validator("bodies")
    @classmethod
    def unique_bodies(
        cls, value: list[CelestialBodySchema]
    ) -> list[CelestialBodySchema]:
        _check_body_ids(body.id for body in value)
        return value

    @model_validator(mode="after")
    def consistent_result(self) -> SimulationResultSchema:
        """Comprueba coherencia del contrato; no repite cálculos de física."""
        first, last = self.samples[0], self.samples[-1]
        if first.t_s != 0:
            raise ValueError("La primera muestra debe tener t_s = 0.")
        if first.spacecraft != self.config.initial_state:
            raise ValueError("La primera muestra debe coincidir con initial_state.")
        if any(b.t_s <= a.t_s for a, b in zip(self.samples, self.samples[1:])):
            raise ValueError("Los tiempos de las muestras deben ser crecientes.")
        if last.t_s > self.config.duration_s:
            raise ValueError("Las muestras no pueden superar duration_s.")
        if self.diagnostics.final_time_s != last.t_s:
            raise ValueError("final_time_s debe coincidir con la última muestra.")
        if self.diagnostics.steps_completed != len(self.samples) - 1:
            raise ValueError("steps_completed debe ser el número de muestras menos uno.")

        if any(b.t_s < a.t_s for a, b in zip(self.events, self.events[1:])):
            raise ValueError("Los eventos deben estar ordenados por tiempo.")
        if any(event.t_s > last.t_s for event in self.events):
            raise ValueError("Los eventos deben estar dentro del intervalo simulado.")

        if self.status == "completed" and last.t_s != self.config.duration_s:
            raise ValueError("completed requiere terminar exactamente en duration_s.")
        if self.status == "collision":
            if not self.events:
                raise ValueError("collision requiere al menos un evento de impacto.")
            # En v1 todos los eventos son impactos terminales. Si hay varios,
            # deben describir el mismo instante y posición final de la nave.
            if any(
                event.t_s != last.t_s
                or event.position_m != last.spacecraft.position_m
                for event in self.events
            ):
                raise ValueError("El impacto debe coincidir con la última muestra.")
        elif self.events:
            raise ValueError("Los eventos collision requieren status = collision.")
        return self

    @classmethod
    def from_domain(cls, result: DomainSimulationResult) -> SimulationResultSchema:
        """Lee atributos de los objetos de dominio y valida antes de responder."""
        return cls.model_validate(result)


# Nombres cómodos para los endpoints; no cambian el contrato JSON.
SimulationRequest = SimulationConfigSchema
SimulationResponse = SimulationResultSchema