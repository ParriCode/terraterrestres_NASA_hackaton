import type { TransferSample, TransferState, Vec3 } from '../types/transfer'

export const clamp = (n: number, min: number, max: number) => Math.max(min, Math.min(max, n))

/** Tangente de un cuerpo en la muestra i por diferencias centradas (el backend no envía su velocidad). */
function bodyTangent(samples: TransferSample[], i: number, key: 'earth' | 'moon'): Vec3 {
  const a = samples[Math.max(0, i - 1)], b = samples[Math.min(samples.length - 1, i + 1)]
  const dt = b.t_s - a.t_s
  return [0, 1, 2].map(k => (b.body_positions_m[key][k] - a.body_positions_m[key][k]) / dt) as Vec3
}

/**
 * Interpolación local entre muestras del backend (sin peticiones ni física nueva).
 * La nave usa Hermite cúbico con posición y velocidad de cada muestra, coherente
 * con la salida densa del backend; Tierra y Luna, Hermite con tangentes estimadas.
 */
export function stateAt(samples: TransferSample[], t: number): TransferState {
  const last = samples.length - 1
  const time = clamp(t, samples[0].t_s, samples[last].t_s)
  let lo = 0, hi = last
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (samples[mid].t_s <= time) lo = mid
    else hi = mid
  }
  const a = samples[lo], b = samples[hi]
  const h = b.t_s - a.t_s
  const s = h > 0 ? (time - a.t_s) / h : 0
  const s2 = s * s, s3 = s2 * s
  const h00 = 2 * s3 - 3 * s2 + 1, h10 = s3 - 2 * s2 + s, h01 = -2 * s3 + 3 * s2, h11 = s3 - s2
  const d00 = (6 * s2 - 6 * s) / h, d10 = 3 * s2 - 4 * s + 1, d01 = (-6 * s2 + 6 * s) / h, d11 = 3 * s2 - 2 * s
  const hermite = (p0: Vec3, v0: Vec3, p1: Vec3, v1: Vec3) =>
    [0, 1, 2].map(i => h00 * p0[i] + h10 * h * v0[i] + h01 * p1[i] + h11 * h * v1[i]) as Vec3
  const body = (key: 'earth' | 'moon') => hermite(a.body_positions_m[key], bodyTangent(samples, lo, key),
    b.body_positions_m[key], bodyTangent(samples, hi, key))
  const position = hermite(a.position_m, a.velocity_m_s, b.position_m, b.velocity_m_s)
  const velocity = [0, 1, 2].map(i => h > 0
    ? d00 * a.position_m[i] + d10 * a.velocity_m_s[i] + d01 * b.position_m[i] + d11 * b.velocity_m_s[i]
    : a.velocity_m_s[i]) as Vec3
  return {
    t_s: time, position_m: position, velocity_m_s: velocity,
    earth_m: body('earth'), moon_m: body('moon'),
  }
}

export const norm = (v: Vec3) => Math.hypot(v[0], v[1], v[2])

const num = (digits: number) => new Intl.NumberFormat('es-ES', { maximumFractionDigits: digits, minimumFractionDigits: digits })
const n0 = num(0), n1 = num(1), n3 = num(3)
export const formatKm = (m: number) => `${n0.format(m / 1000)} km`
export const formatKmS = (ms: number) => `${n3.format(ms / 1000)} km/s`
export const formatMJ = (j: number) => `${n1.format(j / 1e6)} MJ`
const sig3 = new Intl.NumberFormat('es-ES', { maximumSignificantDigits: 3 })
export const formatMeters = (m: number) => m >= 1 ? `${n1.format(m)} m` : m >= 1e-3 ? `${sig3.format(m * 1000)} mm` : `${sig3.format(m * 1e6)} µm`

export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60)
  return `${d} d ${String(h).padStart(2, '0')} h ${String(m).padStart(2, '0')} min`
}

export function formatUtc(date: Date): string {
  return date.toLocaleString('es-ES', {
    timeZone: 'UTC', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }) + ' UTC'
}
