/** Contrato de POST /transfers (backend/app/controllers/transfer_controller.py). Todo en SI. */
export type Vec3 = [number, number, number]
export type TransferObjective = 'energia' | 'distancia'

export type TransferRequest = {
  date: string // ISO 8601 con zona horaria
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
  body_positions_m: { earth: Vec3; moon: Vec3 }
}

export type TransferBody = { name: string; radius_m: number }

export type TransferResponse = {
  source: string
  date: string
  frame: 'earth_moon_barycentric_initial_orbital_plane'
  basis_icrf: number[][]
  objective: TransferObjective
  mass_kg: number
  initial_velocity_m_s: Vec3
  launch_speed_m_s: number
  launch_energy_j: number
  arrival_angle_deg: number // ángulo que eligió el optimizador de /transfers/optimize
  path_length_m: number
  arrival_error_m: number
  duration_s: number
  bodies: { earth: TransferBody; moon: TransferBody }
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
