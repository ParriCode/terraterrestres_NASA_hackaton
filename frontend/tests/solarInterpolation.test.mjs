import test from 'node:test'
import assert from 'node:assert/strict'
import { solarPosition } from '../src/utils/solarInterpolation.ts'
const table = {
  body_id: 'earth', date: '2026-11-15T00:00:00Z', times_s: Array.from({ length:25 }, (_,i)=>i*3600),
  positions_m: Array.from({ length:25 }, (_,i)=>[1e9+2*i*3600,0,0]),
  velocities_m_s: Array.from({ length:25 }, ()=>[2,0,0]),
}
test('hourly NASA states reproduce constant velocity at intervening timestamps',()=>{
  for (const seconds of [0, 123, 3600, 43210, 86400]) {
    const position = solarPosition(table,new Date(Date.parse(table.date)+seconds*1000))
    assert.ok(Math.abs(position[0]-(1e9+2*seconds))<1e-5)
  }
})
test('never extrapolates beyond a downloaded UTC day',()=>{
  assert.throws(()=>solarPosition(table,new Date('2026-11-16T00:01:00Z')))
})
