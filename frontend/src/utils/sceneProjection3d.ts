import { toScene, vMul, vSub } from './icrf3d'
import type { Vector3 } from './icrf3d'
import type { TransferSample } from '../types/transfer'

/** Afín de render únicamente. Permite visualizar Luna, Marte y planetas lejanos
 * sin alterar el marco ICRF, la propagación ni las distancias del backend. */
export function createSpaceFit(samples: TransferSample[], basis: number[][], origin: string, destination: string) {
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity]
  for (const sample of samples) {
    for (const vector of [sample.position_m, sample.body_positions_m[origin], sample.body_positions_m[destination]]) {
      const position = toScene(vector, basis)
      for (let i = 0; i < 3; i++) { min[i] = Math.min(min[i], position[i]); max[i] = Math.max(max[i], position[i]) }
    }
  }
  const center = [0, 1, 2].map(i => samples.length ? (min[i] + max[i]) / 2 : 0) as Vector3
  const span = samples.length ? Math.max(...max.map((value, i) => value - min[i])) : 0
  const scale = Math.min(1, 125 / Math.max(span, 1e-10))
  return {
    center, scale,
    position: (v: readonly number[]) => vMul(vSub(toScene(v, basis), center), scale),
    velocity: (v: readonly number[]) => vMul(toScene(v, basis), scale),
  }
}
