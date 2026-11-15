import type { PointKm } from './icrfProjection'

/** Keep SVG coordinates near the origin and around screen size even for outer planets.
 * Physical coordinates remain untouched; this affine transform is only for rendering.
 */
export function createSceneProjection(points: PointKm[]) {
  const xs = points.map(p => p.x), ys = points.map(p => p.y)
  const minX = points.length ? Math.min(...xs) : 0
  const maxX = points.length ? Math.max(...xs) : 0
  const minY = points.length ? Math.min(...ys) : 0
  const maxY = points.length ? Math.max(...ys) : 0
  const center = { x: (minX + maxX) / 2, y: (minY + maxY) / 2 }
  const kmPerUnit = Math.max(1, (maxX - minX) / 700, (maxY - minY) / 400)
  return {
    kmPerUnit,
    point: (p: PointKm): PointKm => ({ x: (p.x - center.x) / kmPerUnit, y: (p.y - center.y) / kmPerUnit }),
    vector: (p: PointKm): PointKm => ({ x: p.x / kmPerUnit, y: p.y / kmPerUnit }),
  }
}
export type SceneProjection = ReturnType<typeof createSceneProjection>
