import test from 'node:test'
import assert from 'node:assert/strict'
import { frameToIcrf, icrfToEcliptic, eclipticToScreen } from '../src/utils/heliocentric.ts'
import { toScene } from '../src/utils/icrf3d.ts'

const approx = (a, b, tolerance=1e-9) => assert.ok(Math.abs(a-b)<tolerance, `${a} != ${b}`)

test('la base ICRF del backend se reconstruye antes de posicionar una nave a Marte', () => {
  const basis = [[0,1,0],[0,0,1],[1,0,0]]
  const mapped = frameToIcrf([2,3,4],basis)
  assert.deepEqual(mapped,[4,2,3])
})

test('un vector heliocéntrico se convierte ICRF -> eclíptica manteniendo la distancia', () => {
  const v=[1.1e11,-2.2e11,9.8e10]
  const ecliptic=icrfToEcliptic(v)
  approx(Math.hypot(...ecliptic)/1e11, Math.hypot(...v)/1e11)
  const scene=toScene(ecliptic)
  approx(Math.hypot(...scene),Math.hypot(...v)/1e7)
  const screen=eclipticToScreen(ecliptic)
  approx(screen.x,ecliptic[0]/1e9)
})

test('la posición de la nave se obtiene restando el Sol en el mismo instante', () => {
  const sun=[-1.3e11,4.5e10,0]
  const ship=[sun[0]+1.4e11,sun[1]+2.5e10,4.4e9]
  const p=ship.map((x,i)=>x-sun[i])
  const a=icrfToEcliptic(frameToIcrf(p,[[1,0,0],[0,1,0],[0,0,1]]))
  const b=icrfToEcliptic(p)
  a.forEach((x,i)=>approx(x/1e11,b[i]/1e11))
})
