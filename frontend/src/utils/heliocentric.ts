import type { Vec3 } from '../types/transfer'

/** Oblicuidad de la eclíptica J2000 (IAU 1976), en radianes. */
const EPS = 23.439291111 * Math.PI / 180
const COS_EPS = Math.cos(EPS), SIN_EPS = Math.sin(EPS)

/** Unidad de la vista solar: millones de km (1 UA ≈ 149,6). */
export const MKM = 1e9

export type PointMkm = { x: number; y: number }

/**
 * Vector del marco del backend (base orbital Tierra–Luna, filas de basis_icrf = ejes en ICRF)
 * → ICRF ecuatorial. Igual que projectIcrfKm pero conservando las tres componentes.
 */
export function frameToIcrf(v: readonly number[], basis: number[][]): Vec3 {
  const out: Vec3 = [0, 0, 0]
  for (let k = 0; k < basis.length; k++) {
    out[0] += v[k] * basis[k][0]; out[1] += v[k] * basis[k][1]; out[2] += v[k] * basis[k][2]
  }
  return out
}

/** ICRF ecuatorial → eclíptica J2000 (rotación de −ε alrededor de X). */
export function icrfToEcliptic(v: readonly number[]): Vec3 {
  return [v[0], v[1] * COS_EPS + v[2] * SIN_EPS, -v[1] * SIN_EPS + v[2] * COS_EPS]
}

/** Punto de pantalla (Mkm, y hacia abajo) desde un vector eclíptico heliocéntrico en metros. */
export function eclipticToScreen(v: readonly number[]): PointMkm {
  return { x: v[0] / MKM, y: -v[1] / MKM }
}

/**
 * Posición heliocéntrica en pantalla de un punto del backend: se resta la posición del Sol
 * en el MISMO instante (el marco del backend está centrado en el baricentro Tierra–Luna,
 * así que el Sol se mueve en él; sin esta resta la trayectoria aparece deformada).
 */
export function helioScreen(p: readonly number[], sun: readonly number[], basis: number[][]): PointMkm {
  return eclipticToScreen(icrfToEcliptic(frameToIcrf([p[0] - sun[0], p[1] - sun[1], p[2] - sun[2]], basis)))
}
