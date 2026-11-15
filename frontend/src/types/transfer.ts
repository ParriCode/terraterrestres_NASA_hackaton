/** Contrato de POST /transfers (backend/app/controllers/transfer_controller.py). Todo en SI. */
export type Vec3 = [number, number, number]
export type TransferObjective = 'energia' | 'distancia'
export type MissionMode = 'lunar_transfer' | 'lunar_orbit_return'

export type TransferRequest = {
  origin_id?: string
  destination_id?: string
  date: string // ISO 8601 con zona horaria
  mission_mode?: MissionMode
  orbit_altitude_km?: number
  lunar_revolutions?: 1 | 2
  duration_s: number
  launch_angle_deg: number
  objective: TransferObjective
  mass_kg: number
  samples: number
}

export type TransferSample = {
  t_s: number
  position_m: Vec3
  velocity_m_s: Vec3
  body_positions_m: Record<string, Vec3>
}

export type TransferBody = { name: string; radius_m: number }

export type TransferOptimization = {
  method: 'bounded_angle_search'
  attempted_angles_deg: number[]
  valid_candidates: number
  search_complete: boolean
  timed_out_angles_deg: number[]
  global_optimum_guaranteed: false
}

export type LunarManeuver = {
  phase: 'inserción_orbital' | 'inyección_retorno'
  t_s: number
  delta_v_m_s: number
  before_m_s: Vec3
  after_m_s: Vec3
}

export type LunarOrbitReport = {
  altitude_km: number
  revolutions: number
  actual_revolutions: number
  orbit_insertion_t_s: number
  orbit_departure_t_s: number
  orbital_period_s: number
  return_arrival_direction_deg: number
  return_arrival_t_s?: number
  verified_return: boolean
}

export type TransferResponse = {
  mission_mode?: 'lunar_orbit_return'
  return_interface_radius_m?: number
  requested_duration_s?: number // duración máxima, puede regresar antes
  lunar_orbit?: LunarOrbitReport
  maneuvers?: LunarManeuver[]
  total_maneuver_delta_v_m_s?: number
  model_limitations?: string[]
  origin_id?: string
  destination_id?: string
  source: string
  date: string
  frame: 'earth_moon_barycentric_initial_orbital_plane' | 'ssb_ecliptic_j2000_projected'
  basis_icrf: number[][]
  objective: TransferObjective
  mass_kg: number
  initial_velocity_m_s: Vec3
  launch_speed_m_s: number
  launch_energy_j: number
  arrival_angle_deg: number // ángulo que eligió el optimizador de /transfers/optimize
  optimization?: TransferOptimization
  path_length_m: number
  arrival_error_m: number
  duration_s: number
  bodies: Record<string, TransferBody>
  samples: TransferSample[]
}

/** Estado interpolado de la nave y los cuerpos en un instante. */
export type TransferState = {
  t_s: number
  position_m: Vec3
  velocity_m_s: Vec3
  earth_m: Vec3
  moon_m: Vec3
}
