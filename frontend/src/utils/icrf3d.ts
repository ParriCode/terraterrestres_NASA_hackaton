import type { Vec3 } from '../types/transfer'

/** Distancias de representación: 1 unidad WebGL = 10.000 km. */
export const METERS_PER_SCENE_UNIT = 10_000_000
export type Vector3 = [number, number, number]

/**
 * El backend puede entregar coordenadas en el plano orbital inicial o en 3D.
 * basis_icrf contiene los ejes del modelo expresados en coordenadas ICRF.
 * NO confundir los vectores del modelo con coordenadas ICRF sin transformar.
 * Si se omite la base, el vector ya viene de /ephemeris en ICRF.
 * Orientación WebGL: X=ICRF X, Y=ICRF Z, Z=-ICRF Y (sistema dextrógiro).
 */
export function toScene(vector: readonly number[], basis?: readonly (readonly number[])[]): Vector3 {
  if (vector.length !== 3 || vector.some(v => !Number.isFinite(v))) {
    throw new Error('Vector de posición ICRF inválido')
  }
  let x = vector[0], y = vector[1], z = vector[2]
  if (basis) {
    if (![2, 3].includes(basis.length) || basis.some(axis => axis.length !== 3 || axis.some(v => !Number.isFinite(v)))) {
      throw new Error('Base de coordenadas ICRF inválida')
    }
    // Una base de dos filas describe el plano orbital. Su tercera dirección
    // se deduce por producto vectorial para no descartar una componente Z.
    const a = basis[0], b = basis[1]
    const c = basis[2] ?? [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
    x = vector[0] * a[0] + vector[1] * b[0] + vector[2] * c[0]
    y = vector[0] * a[1] + vector[1] * b[1] + vector[2] * c[1]
    z = vector[0] * a[2] + vector[1] * b[2] + vector[2] * c[2]
  }
  return [x / METERS_PER_SCENE_UNIT, z / METERS_PER_SCENE_UNIT, -y / METERS_PER_SCENE_UNIT]
}

export function directionToScene(vector: Vec3): Vector3 {
  // Dirección unitaria: sin reescalado de distancia
  return [vector[0], vector[2], -vector[1]]
}

export function sampleCubic(
  a: readonly number[], va: readonly number[], b: readonly number[], vb: readonly number[],
  dt: number, s: number,
): Vector3 {
  const s2 = s * s, s3 = s2 * s
  const h00 = 2 * s3 - 3 * s2 + 1, h10 = (s3 - 2 * s2 + s) * dt
  const h01 = -2 * s3 + 3 * s2, h11 = (s3 - s2) * dt
  return [0, 1, 2].map(i => h00 * a[i] + h10 * va[i] + h01 * b[i] + h11 * vb[i]) as Vector3
}

export const vAdd = (a: Vector3, b: Vector3): Vector3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
export const vSub = (a: Vector3, b: Vector3): Vector3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
export const vMul = (a: Vector3, s: number): Vector3 => [a[0] * s, a[1] * s, a[2] * s]
export const vDot = (a: Vector3, b: Vector3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
export const vCross = (a: Vector3, b: Vector3): Vector3 => [
  a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0],
]
export const vLength = (a: Vector3): number => Math.hypot(...a)
export const vNormalize = (a: Vector3): Vector3 => {
  const n = vLength(a)
  return n > 1e-12 ? vMul(a, 1 / n) : [0, 1, 0]
}
