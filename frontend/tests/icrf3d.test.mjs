import test from 'node:test'
import assert from 'node:assert/strict'
import { toScene, directionToScene, sampleCubic, METERS_PER_SCENE_UNIT } from '../src/utils/icrf3d.ts'

const close = (actual, expected, tolerance = 1e-9) => {
  assert.equal(actual.length, expected.length)
  actual.forEach((value, i) => assert.ok(Math.abs(value - expected[i]) < tolerance, `componente ${i}: ${value} != ${expected[i]}`))
}

test('ICRF: posiciones geocéntricas no pierden el eje Z', () => {
  close(toScene([1e7,2e7,3e7]), [1,3,-2])
  assert.equal(METERS_PER_SCENE_UNIT,10_000_000)
})

test('base orbital de dos ejes: se transforma a ICRF sin girar la Luna artificialmente', () => {
  // Eje orbital X alineado con ICRF Y; eje orbital Y alineado con ICRF Z.
  const basis = [[0,1,0],[0,0,1]]
  close(toScene([40e7,1e7,0],basis),[0,1,-40])
  // La normal de un plano de 2 ejes es el producto vectorial.
  close(toScene([0,0,2e7],basis),[2,0,0])
})

test('base 3D: las tres componentes de la nave se conservan', () => {
  const basis = [[0,0,1],[0,1,0],[-1,0,0]]
  close(toScene([2e7,3e7,4e7],basis),[-4,2,-3])
})

test('dirección solar ICRF: conserva norma e identificación de ejes', () => {
  close(directionToScene([0,0,1]),[0,1,0])
})

test('Hermite: preserva extremos y reproduce la línea con derivadas coherentes', () => {
  const p0=[1,2,3],p1=[11,7,3],dt=10,velocity=[1,.5,0]
  close(sampleCubic(p0,velocity,p1,velocity,dt,0),p0)
  close(sampleCubic(p0,velocity,p1,velocity,dt,1),p1)
  close(sampleCubic(p0,velocity,p1,velocity,dt,.4),[5,4,3])
})

test('contratos inválidos de coordenadas se rechazan y no se inventa una Luna', () => {
  assert.throws(()=>toScene([1,2]),/inválido/)
  assert.throws(()=>toScene([1,Infinity,0]),/inválido/)
  assert.throws(()=>toScene([1,2,3],[[1,0]]),/inválida/)
})
