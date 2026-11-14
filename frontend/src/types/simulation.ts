/** Contrato compartido v1 (Markdown del equipo). No cambiar campos sin acordarlo con P2*/
export type Vec3 = [number, number, number]
export type SimulationStatus = 'completed' | 'collision' | 'numerical_error'
export type EventType = 'collision'

export interface CelestialBody {
  id: string
  name: string
  mu_m3_s2: number
  radius_m: number
}
export interface SpacecraftState {
  position_m: Vec3
  velocity_m_s: Vec3
}
export interface SimulationConfig {
  scenario_id: string
  initial_state: SpacecraftState
  duration_s: number
  step_s: number
}
export interface TrajectorySample {
  t_s: number
  spacecraft: SpacecraftState
  body_positions_m: Record<string, Vec3>
}
export interface SimulationEvent {
  type: EventType
  t_s: number
  body_id: string
  position_m: Vec3
}
export interface Diagnostics {
  final_time_s: number
  steps_completed: number
  min_distance_m: Record<string, number>
  min_altitude_m: Record<string, number>
}
export interface SimulationResult {
  schema_version: '1.0'
  config: SimulationConfig
  frame: 'earth_moon_barycentric_inertial'
  units: { length: 'm'; time: 's'; velocity: 'm/s'; gravitational_parameter: 'm^3/s^2' }
  bodies: CelestialBody[]
  status: SimulationStatus
  samples: TrajectorySample[]
  events: SimulationEvent[]
  diagnostics: Diagnostics
}

export type JourneyOrigin = 'demo' | 'backend'
export interface Journey {
  id: string
  name: string
  color: string
  visible: boolean
  source: JourneyOrigin
  launch_iso: string
  result: SimulationResult
}

/** Interfaz PROPUESTA para P5 (no forma parte del contrato v1)*/
export interface EphemerisSnapshot {
  epoch_iso: string
  frame: 'ssb_icrf'
  source: string
  positions_m: Record<string, Vec3>
}
