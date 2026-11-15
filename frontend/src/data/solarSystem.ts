/**
 * Planetas para la vista "Sistema solar" (heliocéntrica, a escala real de distancias).
 *
 * Posiciones de referencia: elementos keplerianos medios de JPL (E. M. Standish,
 * "Keplerian Elements for Approximate Positions of the Major Planets", tabla 1, válida
 * 1800–2050). Precisión típica de minutos de arco: frente a Horizons, Tierra y Marte
 * difieren < 0,005° en nov-2026. En una misión a Marte, la Tierra y Marte se dibujan con
 * las posiciones JPL Horizons que devuelve el backend; estos elementos solo se usan para
 * el resto de planetas y para dibujar las órbitas completas.
 */
import type { Vec3 } from '../types/transfer'

export const AU_M = 1.495978707e11

type Elements = [a: number, e: number, i: number, L: number, varpi: number, node: number]
export type Planet = {
  id: string; name: string; asset: string; color: string
  size: number // diámetro del icono en píxeles de pantalla (ampliado, no a escala)
  el: Elements; rate: Elements // valor en J2000 y variación por siglo juliano
}

export const PLANETS: Planet[] = [
  { id: 'mercury', name: 'Mercurio', asset: 'mercurio.svg', color: '#b8b5b2', size: 14,
    el: [0.38709927, 0.20563593, 7.00497902, 252.25032350, 77.45779628, 48.33076593],
    rate: [0.00000037, 0.00001906, -0.00594749, 149472.67411175, 0.16047689, -0.12534081] },
  { id: 'venus', name: 'Venus', asset: 'venus.svg', color: '#f6c68d', size: 19,
    el: [0.72333566, 0.00677672, 3.39467605, 181.97909950, 131.60246718, 76.67984255],
    rate: [0.00000390, -0.00004107, -0.00078890, 58517.81538729, 0.00268329, -0.27769418] },
  { id: 'earth', name: 'Tierra', asset: 'tierra.svg', color: '#66c8ff', size: 22,
    el: [1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0.0],
    rate: [0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0.0] },
  { id: 'mars', name: 'Marte', asset: 'marte.svg', color: '#ea9773', size: 19,
    el: [1.52371034, 0.09339410, 1.84969142, -4.55343205, -23.94362959, 49.55953891],
    rate: [0.00001847, 0.00007882, -0.00813131, 19140.30268499, 0.44441088, -0.29257343] },
  { id: 'jupiter', name: 'Júpiter', asset: 'jupiter.svg', color: '#e4b392', size: 34,
    el: [5.20288700, 0.04838624, 1.30439695, 34.39644051, 14.72847983, 100.47390909],
    rate: [-0.00011607, -0.00013253, -0.00183714, 3034.74612775, 0.21252668, 0.20469106] },
  { id: 'saturn', name: 'Saturno', asset: 'saturno.svg', color: '#f4dfad', size: 44,
    el: [9.53667594, 0.05386179, 2.48599187, 49.95424423, 92.59887831, 113.66242448],
    rate: [-0.00125060, -0.00050991, 0.00193609, 1222.49362201, -0.41897216, -0.28867794] },
  { id: 'uranus', name: 'Urano', asset: 'urano.svg', color: '#81efeb', size: 26,
    el: [19.18916464, 0.04725744, 0.77263783, 313.23810451, 170.95427630, 74.01692503],
    rate: [-0.00196176, -0.00004397, -0.00242939, 428.48202785, 0.40805281, 0.04240589] },
  { id: 'neptune', name: 'Neptuno', asset: 'neptuno.svg', color: '#6294ff', size: 26,
    el: [30.06992276, 0.00859048, 1.77004347, -55.12002969, 44.96476227, 131.78422574],
    rate: [0.00026291, 0.00005105, 0.00035372, 218.45945325, -0.32241464, -0.00508664] },
]

const RAD = Math.PI / 180
const J2000_MS = Date.UTC(2000, 0, 1, 12)

function elementsAt(p: Planet, date: Date) {
  const T = (date.getTime() - J2000_MS) / (36525 * 86400000)
  const [a, e, i, L, varpi, node] = p.el.map((v, k) => v + p.rate[k] * T)
  return { a, e, i: i * RAD, L: L * RAD, w: (varpi - node) * RAD, node: node * RAD, varpi: varpi * RAD }
}

/** Plano orbital (x', y') → eclíptica J2000 heliocéntrica, en metros. */
function rotate(xp: number, yp: number, w: number, node: number, i: number): Vec3 {
  const cw = Math.cos(w), sw = Math.sin(w), cn = Math.cos(node), sn = Math.sin(node), ci = Math.cos(i), si = Math.sin(i)
  return [
    ((cw * cn - sw * sn * ci) * xp + (-sw * cn - cw * sn * ci) * yp) * AU_M,
    ((cw * sn + sw * cn * ci) * xp + (-sw * sn + cw * cn * ci) * yp) * AU_M,
    (sw * si * xp + cw * si * yp) * AU_M,
  ]
}

/** Posición heliocéntrica eclíptica J2000 (m) del planeta en la fecha dada. */
export function planetPosition(p: Planet, date: Date): Vec3 {
  const { a, e, i, L, w, node, varpi } = elementsAt(p, date)
  let M = (L - varpi) % (2 * Math.PI)
  if (M > Math.PI) M -= 2 * Math.PI
  if (M < -Math.PI) M += 2 * Math.PI
  let E = M + e * Math.sin(M)
  for (let k = 0; k < 12; k++) E -= (E - e * Math.sin(E) - M) / (1 - e * Math.cos(E))
  return rotate(a * (Math.cos(E) - e), a * Math.sqrt(1 - e * e) * Math.sin(E), w, node, i)
}

/** Órbita completa (elipse) del planeta en la fecha dada, para dibujar. */
export function planetOrbit(p: Planet, date: Date, n = 240): Vec3[] {
  const { a, e, i, w, node } = elementsAt(p, date)
  const b = a * Math.sqrt(1 - e * e)
  return Array.from({ length: n + 1 }, (_, k) => {
    const E = (2 * Math.PI * k) / n
    return rotate(a * (Math.cos(E) - e), b * Math.sin(E), w, node, i)
  })
}

export const bodyName = (id: string) => id === 'sun' ? 'Sol' : id === 'moon' ? 'Luna' : PLANETS.find(p => p.id === id)?.name ?? id
