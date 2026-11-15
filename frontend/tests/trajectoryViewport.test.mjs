import assert from 'node:assert/strict'
import test from 'node:test'
import { createSceneProjection } from '../src/utils/trajectoryViewport.ts'

for (const distanceKm of [384400, 795000000, 4500000000]) {
  test(`keeps a ${distanceKm} km journey inside a small SVG coordinate range`, () => {
    const points = [{ x: -1e9, y: 2e9 }, { x: -1e9 + distanceKm, y: 2e9 - distanceKm / 2 }]
    const scene = createSceneProjection(points)
    for (const point of points.map(scene.point)) {
      assert.ok(Math.abs(point.x) <= 350)
      assert.ok(Math.abs(point.y) <= 200)
    }
    const delta = scene.vector({ x: distanceKm, y: -distanceKm / 2 })
    const a = scene.point(points[0]), b = scene.point(points[1])
    assert.ok(Math.abs((b.x - a.x) - delta.x) < 1e-9)
    assert.ok(Math.abs((b.y - a.y) - delta.y) < 1e-9)
    assert.ok(Math.abs(delta.x * scene.kmPerUnit - distanceKm) < .001)
  })
}

test('coincident and empty positions have a finite scale', () => {
  for (const points of [[], [{ x: 10, y: 20 }, { x: 10, y: 20 }]]) {
    const scene = createSceneProjection(points)
    assert.ok(Number.isFinite(scene.kmPerUnit) && scene.kmPerUnit > 0)
    assert.deepEqual(scene.vector({ x: 0, y: 0 }), { x: 0, y: 0 })
  }
})
