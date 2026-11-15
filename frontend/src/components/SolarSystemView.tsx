import { useEffect, useRef, useState } from 'react'
import { BODIES, bodyName } from '../data/solarSystem'
import { cachedSolarDay, subscribeSolarDay } from '../api/solarPreview'
import { solarPosition } from '../utils/solarInterpolation'
import type { SolarSnapshot } from '../api/solarPreview'

type Props = { date: Date; journeyCount: number; origin: string; destination: string; pickTarget: 'origin' | 'destination'; onSelect: (id: string) => void }
export default function SolarSystemView({ date, origin, destination, pickTarget, onSelect }: Props) {
  const day = date.toISOString().slice(0, 10)
  const [result, setResult] = useState<SolarSnapshot | null>(null)
  const [zoom, setZoom] = useState(1)
  const [center, setCenter] = useState({ x: 700, y: 395 })
  const drag = useRef<{ x: number; y: number } | null>(null)
  useEffect(() => {
    let unsubscribe: (() => void) | undefined
    const timer = window.setTimeout(() => { unsubscribe = subscribeSolarDay(day, setResult) }, 150)
    return () => { clearTimeout(timer); unsubscribe?.() }
  }, [day])
  const current = result?.day === day ? result : cachedSolarDay(day)
  const positions = current ? Object.fromEntries(Object.entries(current.tables).map(([id, table]) => [id, solarPosition(table, date)])) : undefined
  const sun = positions?.sun
  const points = positions && sun ? BODIES.filter(b => positions[b.id]).map(b => {
    const p = positions[b.id], x = p[0] - sun[0], y = p[1] - sun[1]
    const r = Math.hypot(x, y), radius = 105 * Math.log1p(r / 149597870700 * 3)
    const px = 700 + (r ? x / r * radius : 0), py = 395 - (r ? y / r * radius : 0)
    return { ...b, anchorX: px, anchorY: py, x: px + (b.id === 'moon' ? 35 : 0), y: py + (b.id === 'moon' ? 35 : 0) }
  }) : []
  return <div className="solar-view">
    <svg className="map-svg" viewBox={`${center.x - 700 / zoom} ${center.y - 395 / zoom} ${1400 / zoom} ${790 / zoom}`}
      onWheel={e => setZoom(v => Math.max(.5, Math.min(80, v * (e.deltaY < 0 ? 1.2 : 1/1.2))))}
      onPointerDown={e => { if ((e.target as Element).closest('[role="button"]')) return; drag.current = { x: e.clientX, y: e.clientY }; e.currentTarget.setPointerCapture(e.pointerId) }}
      onPointerMove={e => { if (!drag.current) return; const scale = Math.max(1400 / e.currentTarget.clientWidth, 790 / e.currentTarget.clientHeight) / zoom; const dx = e.clientX-drag.current.x, dy = e.clientY-drag.current.y; setCenter(c => ({ x: c.x-dx*scale, y:c.y-dy*scale })); drag.current = { x:e.clientX, y:e.clientY } }}
      onPointerUp={() => { drag.current = null }} onPointerCancel={() => { drag.current = null }} aria-label="Cuerpos del sistema solar según NASA/JPL">
      <rect x="-5000" y="-5000" width="10000" height="10000" fill="#071326" />
      {points.map(b => <g key={b.id} role="button" tabIndex={0} aria-label={`Elegir ${bodyName(b.id)} como ${pickTarget === 'origin' ? 'origen' : 'destino'}`}
        style={{ cursor: 'pointer' }} onClick={() => onSelect(b.id)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(b.id) } }}>
        {b.id === 'moon' && <line x1={b.anchorX} y1={b.anchorY} x2={b.x} y2={b.y} stroke="#8fa5ba" />}
        <circle cx={b.x} cy={b.y} r={b.size / 2 + 6} fill="#10263b" stroke={b.id === origin ? '#64ead5' : b.id === destination ? '#f7ba68' : b.color} strokeWidth={b.id === origin || b.id === destination ? 3 : 1} />
        <image href={`/resource/${b.asset}`} x={b.x - b.size / 2} y={b.y - b.size / 2} width={b.size} height={b.size} pointerEvents="none" />
        <text x={b.x} y={b.y + b.size / 2 + 18} className="planet-label" fontSize={13}>{b.name}</text>
      </g>)}
    </svg>
    <div className="scene-heading"><span className="eyebrow">NASA/JPL HORIZONS</span><h1>Elige tu {pickTarget === 'origin' ? 'origen' : 'destino'}</h1>
      <p>{current?.error ?? (current?.loading ? `Cargando NASA: ${Object.keys(current.tables).length}/${BODIES.length} cuerpos…` : positions ? `${bodyName(origin)} → ${bodyName(destination)} · Pulsa un cuerpo o usa los selectores.` : 'Consultando posiciones NASA…')}</p></div>
    <div className="map-tools"><button className="icon-button" onClick={() => setZoom(v => Math.min(80, v * 1.4))} aria-label="Acercar">+</button><button className="icon-button" onClick={() => setZoom(v => Math.max(.5, v / 1.4))} aria-label="Alejar">−</button><button className="icon-button" onClick={() => { setZoom(1); setCenter({ x:700, y:395 }) }} aria-label="Encuadrar">⌖</button></div>
    <div className="view-legend">Posiciones interpoladas de muestras horarias NASA · Proyección eclíptica 2D · Distancias comprimidas logarítmicamente · Iconos ampliados; Luna desplazada con línea guía · Arrastra para mover</div>
  </div>
}
