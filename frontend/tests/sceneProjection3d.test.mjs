import test from 'node:test'
import assert from 'node:assert/strict'
import { createSpaceFit } from '../src/utils/sceneProjection3d.ts'
import { toScene, vLength, vSub } from '../src/utils/icrf3d.ts'
import { SolarSpaceRenderer } from '../src/renderer/SpaceRenderer.ts'
const basis=[[1,0,0],[0,1,0]]
const sample=(origin,destination,pos,t=0,ids=['earth','mars'])=>({t_s:t,position_m:pos,velocity_m_s:[0,0,0],body_positions_m:{[ids[0]]:origin,[ids[1]]:destination}})
test('Tierra a Marte: el encuadre 3D contiene el recorrido y conserva las posiciones relativas',()=>{
 const origin=[1.3e11,0,0],destination=[-2.1e11,1.0e11,0]
 const samples=[sample(origin,destination,origin),sample(origin,destination,[-4e10,5e10,0],1),sample(origin,destination,destination,2)]
 const fit=createSpaceFit(samples,basis,'earth','mars')
 assert.ok(fit.scale<.05)
 for(const s of samples)for(const vec of [s.position_m,...Object.values(s.body_positions_m)]) {
   const point=fit.position(vec)
   assert.ok(point.every(n=>Number.isFinite(n)&&Math.abs(n)<=62.6))
 }
 const dBefore=vLength(vSub(toScene(destination,basis),toScene(origin,basis)))
 const dAfter=vLength(vSub(fit.position(destination),fit.position(origin)))
 assert.ok(Math.abs(dAfter/dBefore-fit.scale)<1e-12)
})
test('Tierra a Luna: no se comprime arbitrariamente una separación de 384400 km',()=>{
 const origin=[0,0,0],dest=[384400000,0,0]
 const fit=createSpaceFit([sample(origin,dest,origin,0,['earth','moon']),sample(origin,dest,dest,1,['earth','moon'])],basis,'earth','moon')
 assert.equal(fit.scale,1)
 assert.ok(Math.abs(vLength(vSub(fit.position(dest),fit.position(origin)))-38.44)<1e-9)
})
test('Mapa 3D heliocéntrico: Marte y Neptuno se sitúan en orden sin salir del encuadre',()=>{
 const au=14959.78707
 const mars=SolarSpaceRenderer.position([au*1.52,0,0])
 const neptune=SolarSpaceRenderer.position([au*30,0,0])
 assert.ok(mars[0]>20 && neptune[0]>mars[0] && neptune[0]<100)
 assert.deepEqual(SolarSpaceRenderer.position([0,0,0]),[0,0,0])
})
