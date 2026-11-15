/** Proyección 2D para la pantalla del marco inercial ICRF (XY).
 * El backend integra la nave en el plano orbital inicial girado.
 * basis_icrf = [ejeX_en_ICRF, ejeY_en_ICRF], cada uno con tres componentes.
 * Deshacer la rotación SOLO para dibujar: no altera la física ni el JSON.
 */
export type PointKm = { x: number; y: number }
export type BasisICRF = [number[], number[]]

export function projectIcrfKm(vector: readonly number[], basis?: number[][]): PointKm {
  if (basis) {
    if (![2, 3].includes(basis.length) || basis.some(axis => axis.length !== 3 || axis.some(v => !Number.isFinite(v)))) {
      throw new Error('El backend devolvió una base ICRF inválida.')
    }
    return {
      x: (vector[0] * basis[0][0] + vector[1] * basis[1][0] + (basis.length === 3 ? vector[2] * basis[2][0] : 0)) / 1000,
      y: -(vector[0] * basis[0][1] + vector[1] * basis[1][1] + (basis.length === 3 ? vector[2] * basis[2][1] : 0)) / 1000,
    }
  }
  // La vista previa ya está expresada en ICRF sin rotar.
  return { x: vector[0] / 1000, y: -vector[1] / 1000 }
}
