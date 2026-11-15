import type { TransferSample, Vec3 } from '../types/transfer'

/** μ del Sol (m³/s²), mismo valor que el catálogo del backend. */
export const MU_SUN = 1.32712440041939e20

const sub = (a: readonly number[], b: readonly number[]): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
const dot = (a: readonly number[], b: readonly number[]) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
const cross = (a: readonly number[], b: readonly number[]): Vec3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
const scale = (a: readonly number[], k: number): Vec3 => [a[0] * k, a[1] * k, a[2] * k]
const norm = (a: readonly number[]) => Math.hypot(a[0], a[1], a[2])

/**
 * Órbita kepleriana completa (elipse) de un cuerpo alrededor del Sol a partir de su estado
 * heliocéntrico (r, v). Solo para dibujar la órbita entera: las posiciones de la misión
 * proceden siempre del backend (JPL Horizons). Devuelve puntos en el marco del backend,
 * desplazados a la posición del Sol `sunPos`.
 */
export function keplerOrbit(r: Vec3, v: Vec3, sunPos: readonly number[], mu = MU_SUN, n = 360): Vec3[] {
  const rn = norm(r)
  const energy = dot(v, v) / 2 - mu / rn
  if (!(energy < 0)) return []
  const a = -mu / (2 * energy)
  const h = cross(r, v)
  const eVec = sub(scale(cross(v, h), 1 / mu), scale(r, 1 / rn))
  const e = norm(eVec)
  const P = e > 1e-10 ? scale(eVec, 1 / e) : scale(r, 1 / rn)
  const hn = norm(h)
  const Q = scale(cross(h, P), 1 / hn)
  const b = a * Math.sqrt(1 - e * e)
  const points: Vec3[] = []
  for (let i = 0; i <= n; i++) {
    const E = (2 * Math.PI * i) / n
    const x = a * (Math.cos(E) - e), y = b * Math.sin(E)
    points.push([sunPos[0] + x * P[0] + y * Q[0], sunPos[1] + x * P[1] + y * Q[1], sunPos[2] + x * P[2] + y * Q[2]])
  }
  return points
}

/** Estado heliocéntrico de un cuerpo en la primera muestra (velocidad por diferencias). */
export function heliocentricState(samples: TransferSample[], key: 'earth' | 'mars'): { r: Vec3; v: Vec3; sun: Vec3 } | null {
  const a = samples[0], b = samples[1]
  const pa = a?.body_positions_m[key], pb = b?.body_positions_m[key]
  const sa = a?.body_positions_m.sun, sb = b?.body_positions_m.sun
  if (!pa || !pb || !sa || !sb) return null
  const dt = b.t_s - a.t_s
  return { r: sub(pa, sa), v: scale(sub(sub(pb, sb), sub(pa, sa)), 1 / dt), sun: sa }
}
