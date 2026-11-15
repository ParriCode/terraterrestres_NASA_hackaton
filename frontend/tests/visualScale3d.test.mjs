import test from 'node:test'
import assert from 'node:assert/strict'
import { capBodyRadius, shipScaleForClearance } from '../src/utils/visualScale3d.ts'

test('Vista previa: puede ampliar la Luna cuando no hay trayectoria', () => {
  assert.equal(capBodyRadius(.17374,5.3,Infinity), .17374*5.3)
})
test('Una órbita lunar a 100 km mantiene la superficie fuera de la trayectoria', () => {
  const r=.17374, d=r+.01
  const shown=capBodyRadius(r,5.3,d)
  assert.equal(shown, d-.001)
  const shipScale=shipScaleForClearance(d-shown,.115)
  assert.ok(shipScale>0)
  assert.ok(.95*shipScale < d-shown)
})
test('Cuando la trayectoria se mantiene lejos, los radios deseados permanecen', () => {
  assert.equal(capBodyRadius(.17374,5.3,12), .17374*5.3)
  assert.equal(shipScaleForClearance(3,.115),.115)
})
test('El modelo no mueve el cohete cuando el backend anuncia una colisión real', () => {
  const radius=.17374
  const shown=capBodyRadius(radius,5.3,radius-.03)
  assert.equal(shown,radius)
  assert.equal(shipScaleForClearance(radius-.03-shown,.115),0)
})
test('No se dibuja una malla gigante dentro de la Luna', () => {
  for(const distance of [.174,.18,.2,.4,1,5]) {
    const body=capBodyRadius(.17374,5.3,distance)
    const rocket=shipScaleForClearance(distance-body,.115)
    assert.ok(rocket*.95 < distance-body,`distancia=${distance}`)
  }
})
