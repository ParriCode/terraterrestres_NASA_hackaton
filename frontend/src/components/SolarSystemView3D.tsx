import { useEffect, useRef, useState } from 'react'
import { BODIES, bodyName } from '../data/solarSystem'
import { cachedSolarDay, subscribeSolarDay } from '../api/solarPreview'
import type { SolarSnapshot } from '../api/solarPreview'
import { solarPosition } from '../utils/solarInterpolation'
import { SolarSpaceRenderer } from '../renderer/SpaceRenderer'
import Icon from './Icon'

type Props = {date:Date;journeyCount:number;origin:string;destination:string;pickTarget:'origin'|'destination';onSelect:(id:string)=>void}

export default function SolarSystemView3D({date,origin,destination,pickTarget,onSelect}:Props){
  const day=date.toISOString().slice(0,10)
  const [result,setResult]=useState<SolarSnapshot|null>(null)
  const [error,setError]=useState('')
  const canvas=useRef<HTMLCanvasElement>(null)
  const renderer=useRef<SolarSpaceRenderer|null>(null)
  const labels=useRef<Record<string,HTMLButtonElement|null>>({})
  useEffect(()=>{
    let unsubscribe:(()=>void)|undefined
    const timeout=setTimeout(()=>{unsubscribe=subscribeSolarDay(day,setResult)},150)
    return ()=>{clearTimeout(timeout);unsubscribe?.()}
  },[day])
  const current=result?.day===day?result:cachedSolarDay(day)
  const positions=current?Object.fromEntries(Object.entries(current.tables).map(([id,table])=>[id,solarPosition(table,date)])):null
  useEffect(()=>{
    if(!canvas.current)return
    try {
      const view=new SolarSpaceRenderer(canvas.current,labels.current)
      renderer.current=view;setError('')
      return ()=>{view.dispose();if(renderer.current===view)renderer.current=null}
    }catch(e){setError(e instanceof Error?e.message:'No se pudo inicializar WebGL')}
  },[])
  useEffect(()=>{renderer.current?.setBodies(positions,date)},[positions,date])
  return <div className="solar-3d-view">
    <canvas className="space-canvas" ref={canvas} aria-label="Sistema solar 3D con planetas en posiciones NASA/JPL. Arrastra para girar, rueda para zoom." />
    <div className="solar-3d-labels">{BODIES.map(b=><button type="button" key={b.id}
      ref={el=>{labels.current[b.id]=el}} style={{display:'none'}}
      className={`solar-3d-label ${b.id===origin?'is-origin':b.id===destination?'is-destination':''}`}
      title={`Seleccionar ${b.name} como ${pickTarget==='origin'?'origen':'destino'}`}
      onClick={()=>onSelect(b.id)}>{b.name}</button>)}</div>
    <div className="scene-heading"><span className="eyebrow">NASA/JPL HORIZONS · 3D</span>
      <h1>Elige tu {pickTarget==='origin'?'origen':'destino'}</h1>
      <p>{current?.error??(current?.loading?`Cargando posiciones de NASA: ${Object.keys(current.tables).length}/${BODIES.length} cuerpos…`:positions?`${bodyName(origin)} → ${bodyName(destination)} · Elige un cuerpo en la escena.`:'Consultando posiciones reales…')}</p></div>
    <div className="map-tools space-controls">
      <button type="button" className="icon-button" aria-label="Acercar" onClick={()=>renderer.current?.zoom(.7)}><Icon name="plus" /></button>
      <button type="button" className="icon-button" aria-label="Alejar" onClick={()=>renderer.current?.zoom(1.4)}><Icon name="minus" /></button>
      <button type="button" className="icon-button" aria-label="Encuadrar sistema solar" onClick={()=>renderer.current?.home()}><Icon name="crosshair" /></button>
      <button type="button" className="icon-button" aria-label="Enfocar Marte" title="Enfocar Marte" onClick={()=>renderer.current?.focus('mars')}>♂</button>
      <button type="button" className="icon-button" aria-label="Enfocar Tierra" title="Enfocar Tierra" onClick={()=>renderer.current?.focus('earth')}>🌍</button>
    </div>
    {error&&<div className="space-render-error" role="alert"><strong>No se puede mostrar el sistema solar 3D</strong><p>{error}</p></div>}
    <div className="view-legend space-legend">Posiciones ICRF interpoladas de NASA/JPL · Distancias heliocéntricas comprimidas · Luna desplazada visualmente · Tamaños ampliados · Arrastra para girar</div>
  </div>
}
