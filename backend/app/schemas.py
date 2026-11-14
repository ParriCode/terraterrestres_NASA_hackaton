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
    """Evento calculado por Li. En v1 solo existe collision."""

    type: EventType
    t_s: NonNegativeNumber
    body_id: BodyId
    position_m: Vec3


class DiagnosticsSchema(_Schema):
    """Resumen de Angel; los mínimos se estiman sobre las muestras guardadas."""

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