import type { TransferSample, TransferState, Vec3 } from '../types/transfer'

export const clamp = (n: number, min: number, max: number) => Math.max(min, Math.min(max, n))

/** Devuelve el índice inferior `lo` tal que samples[lo].t_s <= time <= samples[lo + 1].t_s. */
export function findSampleInterval(samples: TransferSample[], time: number): number {
  const last = samples.length - 1
  if (last <= 1 || time <= samples[0].t_s) return 0
  if (time >= samples[last].t_s) return last - 1
  let lo = 0, hi = last
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (samples[mid].t_s <= time) lo = mid
    else hi = mid
  }
  return lo
}

/** Tangente de un cuerpo en la muestra i por diferencias centradas (el backend no envía su velocidad). */
function bodyTangent(samples: TransferSample[], i: number, key: 'earth' | 'moon'): Vec3 {
  const a = samples[Math.max(0, i - 1)], b = samples[Math.min(samples.length - 1, i + 1)]
  const invDt = 1 / (b.t_s - a.t_s)
  const pa = a.body_positions_m[key], pb = b.body_positions_m[key]
  return [(pb[0] - pa[0]) * invDt, (pb[1] - pa[1]) * invDt, (pb[2] - pa[2]) * invDt]
}

function hermiteVec3(
  p0: Vec3, v0: Vec3, p1: Vec3, v1: Vec3,
  h00: number, h10h: number, h01: number, h11h: number,
): Vec3 {
  return [
    h00 * p0[0] + h10h * v0[0] + h01 * p1[0] + h11h * v1[0],
    h00 * p0[1] + h10h * v0[1] + h01 * p1[1] + h11h * v1[1],
    h00 * p0[2] + h10h * v0[2] + h01 * p1[2] + h11h * v1[2],
  ]
}

/**
 * Interpolación local entre muestras del backend (sin peticiones ni física nueva).
 * La nave usa Hermite cúbico con posición y velocidad de cada muestra, coherente
 * con la salida densa del backend; Tierra y Luna, Hermite con tangentes estimadas.
 */
export function stateAt(samples: TransferSample[], t: number): TransferState {
  const last = samples.length - 1
  const time = clamp(t, samples[0].t_s, samples[last].t_s)
  const lo = findSampleInterval(samples, time)
  const a = samples[lo], b = samples[lo + 1]
  const h = b.t_s - a.t_s
  const s = h > 0 ? (time - a.t_s) / h : 0
  const s2 = s * s, s3 = s2 * s
  const h00 = 2 * s3 - 3 * s2 + 1
  const h10h = (s3 - 2 * s2 + s) * h
  const h01 = -2 * s3 + 3 * s2
  const h11h = (s3 - s2) * h

  const position = hermiteVec3(a.position_m, a.velocity_m_s, b.position_m, b.velocity_m_s, h00, h10h, h01, h11h)
  const velocity: Vec3 = h > 0
    ? (() => {
        const d00 = (6 * s2 - 6 * s) / h
        const d10 = 3 * s2 - 4 * s + 1
        const d01 = (-6 * s2 + 6 * s) / h
        const d11 = 3 * s2 - 2 * s
        return [
          d00 * a.position_m[0] + d10 * a.velocity_m_s[0] + d01 * b.position_m[0] + d11 * b.velocity_m_s[0],
          d00 * a.position_m[1] + d10 * a.velocity_m_s[1] + d01 * b.position_m[1] + d11 * b.velocity_m_s[1],
          d00 * a.position_m[2] + d10 * a.velocity_m_s[2] + d01 * b.position_m[2] + d11 * b.velocity_m_s[2],
        ]
      })()
    : [a.velocity_m_s[0], a.velocity_m_s[1], a.velocity_m_s[2]]

  const earth = hermiteVec3(
    a.body_positions_m.earth, bodyTangent(samples, lo, 'earth'),
    b.body_positions_m.earth, bodyTangent(samples, lo + 1, 'earth'),
    h00, h10h, h01, h11h,
  )
  const moon = hermiteVec3(
    a.body_positions_m.moon, bodyTangent(samples, lo, 'moon'),
    b.body_positions_m.moon, bodyTangent(samples, lo + 1, 'moon'),
    h00, h10h, h01, h11h,
  )

  return { t_s: time, position_m: position, velocity_m_s: velocity, earth_m: earth, moon_m: moon }
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