import type { Vec3 } from '../types/transfer'
export type SolarTable = { body_id: string; date: string; times_s: number[]; positions_m: Vec3[]; velocities_m_s: Vec3[] }

/** Cubic Hermite interpolation of NASA's hourly position/velocity samples. */
export function solarPosition(table: SolarTable, date: Date): Vec3 {
  const t = (date.getTime() - Date.parse(table.date)) / 1000
  if (t < 0 || t > 86400) throw new Error('Fecha fuera de la tabla NASA.')
  const i = Math.min(23, Math.floor(t / 3600)), u = (t - i * 3600) / 3600
  const u2 = u*u, u3 = u2*u
  const p = table.positions_m[i].map((v, axis) =>
    (2*u3-3*u2+1)*v + (u3-2*u2+u)*3600*table.velocities_m_s[i][axis]
    + (-2*u3+3*u2)*table.positions_m[i+1][axis] + (u3-u2)*3600*table.velocities_m_s[i+1][axis])
  const eps = 23.439291111 * Math.PI / 180
  return [p[0], p[1]*Math.cos(eps) + p[2]*Math.sin(eps), 0]
}
