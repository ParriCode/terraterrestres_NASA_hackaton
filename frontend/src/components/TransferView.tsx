import { useMemo, useRef, useState } from 'react'
import type { PointerEvent, WheelEvent } from 'react'
import type { TransferResponse, TransferSample, TransferState } from '../types/transfer'
import { clamp } from '../utils/transfer'
import Icon from './Icon'

type Props = { transfer: TransferResponse | null; state: TransferState | null; time: number; visible?: boolean; color?: string; onSolar: () => void }
type Box = { x: number; y: number; w: number; h: number }
type Point = { x: number; y: number }
const W = 1000, H = 640
const PREVIEW: Box = { x: -104000, y: -187000, w: 590000, h: 377600 }
const toKm = (v: readonly number[]): Point => ({ x: v[0] / 1000, y: -v[1] / 1000 })
const f = (n: number) => n.toFixed(2)
const polyline = (points: Point[]) => points.map(p => `${f(p.x)},${f(p.y)}`).join(' ')

/** Curva Hermite visual. Los puntos y velocidades provienen EXCLUSIVAMENTE del backend. */
function makePath(samples: TransferSample[]): string {
  if (!samples.length) return ''
  let d = `M${f(samples[0].position_m[0] / 1000)},${f(-samples[0].position_m[1] / 1000)}`
  for (let i = 1; i < samples.length; i++) {
    const a = samples[i - 1], b = samples[i], k = (b.t_s - a.t_s) / 3000
    d += ` C${f(a.position_m[0] / 1000 + a.velocity_m_s[0] * k)},${f(-(a.position_m[1] / 1000 + a.velocity_m_s[1] * k))}`
      + ` ${f(b.position_m[0] / 1000 - b.velocity_m_s[0] * k)},${f(-(b.position_m[1] / 1000 - b.velocity_m_s[1] * k))}`
      + ` ${f(b.position_m[0] / 1000)},${f(-b.position_m[1] / 1000)}`
  }
  return d
}

export default function TransferView({ transfer, state, time, visible = true, color = '#70efd8', onSolar }: Props) {
  const svg = useRef<SVGSVGElement>(null)
  const drag = useRef<{ x: number; y: number; box: Box } | null>(null)
  const geometry = useMemo(() => {
    if (!transfer) return { earth: '', moon: '', home: PREVIEW }
    const ship = transfer.samples.map(s => toKm(s.position_m))
    const earth = transfer.samples.map(s => toKm(s.body_positions_m.earth))
    const moon = transfer.samples.map(s => toKm(s.body_positions_m.moon))
    const all = [...ship, ...earth, ...moon]
    const pad = 35000
    const minX = Math.min(...all.map(p => p.x)) - pad, maxX = Math.max(...all.map(p => p.x)) + pad
    const minY = Math.min(...all.map(p => p.y)) - pad, maxY = Math.max(...all.map(p => p.y)) + pad
    const scale = Math.max((maxX - minX) / W, (maxY - minY) / H)
    const w = W * scale, h = H * scale
    return { earth: polyline(earth), moon: polyline(moon), home: { x: (minX + maxX - w) / 2, y: (minY + maxY - h) / 2, w, h } }
  }, [transfer])
  const [view, setView] = useState<{ key: TransferResponse | null; box: Box }>({ key: transfer, box: geometry.home })
  const box = view.key === transfer ? view.box : geometry.home
  const setBox = (next: Box) => setView({ key: transfer, box: next })
  const unit = box.w / W

  const segments = useMemo(() => {
    if (!transfer || !state) return { past: '', future: '' }
    const samples = transfer.samples
    const now: TransferSample = {
      t_s: clamp(time, samples[0].t_s, samples[samples.length - 1].t_s),
      position_m: state.position_m, velocity_m_s: state.velocity_m_s,
      body_positions_m: { earth: state.earth_m, moon: state.moon_m },
    }
    const past = samples.filter(s => s.t_s < now.t_s)
    const future = samples.filter(s => s.t_s > now.t_s)
    return { past: makePath([...past, now]), future: makePath([now, ...future]) }
  }, [transfer, state, time])

  function toWorld(e: { clientX: number; clientY: number }) {
    if (!svg.current) return { x: box.x + box.w / 2, y: box.y + box.h / 2 }
    const matrix = svg.current.getScreenCTM()
    if (!matrix) return { x: box.x + box.w / 2, y: box.y + box.h / 2 }
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(matrix.inverse())
    return { x: p.x, y: p.y }
  }
  function zoom(factor: number, anchor = { x: box.x + box.w / 2, y: box.y + box.h / 2 }) {
    const w = clamp(box.w * factor, 1200, geometry.home.w * 5)
    const scale = w / box.w
    setBox({ x: anchor.x - (anchor.x - box.x) * scale, y: anchor.y - (anchor.y - box.y) * scale, w, h: box.h * scale })
  }
  function pointerDown(e: PointerEvent<SVGSVGElement>) {
    if (e.button !== 0) return
    e.preventDefault()
    drag.current = { x: e.clientX, y: e.clientY, box }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  function pointerMove(e: PointerEvent<SVGSVGElement>) {
    if (!drag.current || !svg.current) return
    const rect = svg.current.getBoundingClientRect()
    const b = drag.current.box, s = Math.max(b.w / rect.width, b.h / rect.height)
    setBox({ ...b, x: b.x - (e.clientX - drag.current.x) * s, y: b.y - (e.clientY - drag.current.y) * s })
  }

  // Sin transferencia: ubicación de referencia de la Luna para presentar la navegación, no una efeméride.
  const earth = state ? toKm(state.earth_m) : { x: 0, y: 0 }
  const moon = state ? toKm(state.moon_m) : { x: 384400, y: 0 }
  const ship = state ? toKm(state.position_m) : null
  const rEarth = (transfer?.bodies.earth.radius_m ?? 6371000) / 1000
  const rMoon = (transfer?.bodies.moon.radius_m ?? 1737400) / 1000
  const visualEarth = Math.max(rEarth, 21 * unit)
  const visualMoon = Math.max(rMoon, 13 * unit)
  const shipIconSize = 26 * unit
  const closeToShip = box.w < 130000
  const velocity = state ? toKm(state.velocity_m_s) : null
  const speed = velocity ? Math.hypot(velocity.x, velocity.y) : 0
  const arrow = speed > 0 ? 55 * unit * Math.min(3, speed) / speed : 0

  return <div className="transfer-view">
    <svg ref={svg} className="map-svg" viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`} preserveAspectRatio="xMidYMid meet"
      onWheel={(e: WheelEvent<SVGSVGElement>) => { e.preventDefault(); zoom(e.deltaY < 0 ? .83 : 1.2, toWorld(e)) }}
      onPointerDown={pointerDown} onPointerMove={pointerMove}
      onPointerUp={() => { drag.current = null }} onPointerCancel={() => { drag.current = null }}
      onLostPointerCapture={() => { drag.current = null }} onDragStart={e => e.preventDefault()}
      role="img" aria-label={transfer ? 'Trayectoria científica Tierra–Luna en plano baricéntrico' : 'Vista ilustrativa de Tierra y Luna'}>
      <defs><marker id="arrow-head" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" fill="#ffbd69" /></marker></defs>
      {!transfer && <circle cx="0" cy="0" r="384400" fill="none" stroke="#6e88a9" strokeWidth={1.5 * unit} strokeDasharray={`${5 * unit} ${9 * unit}`} opacity=".42" />}
      {transfer && <>
        <polyline points={geometry.earth} className="body-track earth-track" strokeWidth={1.2 * unit} />
        <polyline points={geometry.moon} className="body-track moon-track" strokeWidth={1.2 * unit} strokeDasharray={`${6 * unit} ${6 * unit}`} />
        {visible && <>
          <path d={segments.future} className="ship-track ship-track-future" stroke={color} strokeWidth={2.4 * unit} strokeDasharray={`${7 * unit} ${9 * unit}`} />
          <path d={segments.past} className="ship-track ship-track-past" stroke={color} strokeWidth={3.2 * unit} />
        </>}
      </>}
      <circle cx={earth.x} cy={earth.y} r={visualEarth * 1.2} className="earth-glow" />
      <image href="/resource/tierra.svg" x={earth.x - visualEarth} y={earth.y - visualEarth} width={visualEarth * 2} height={visualEarth * 2} />
      <circle cx={earth.x} cy={earth.y} r={rEarth} fill="none" stroke="#64d9ff" strokeWidth={1.3 * unit} />
      <text x={earth.x} y={earth.y + visualEarth + 20 * unit} fontSize={13 * unit} className="body-label">Tierra</text>
      <image href="/resource/luna.svg" x={moon.x - visualMoon} y={moon.y - visualMoon} width={visualMoon * 2} height={visualMoon * 2} />
      <circle cx={moon.x} cy={moon.y} r={rMoon} fill="none" stroke="#dadce5" strokeWidth={1.2 * unit} />
      <text x={moon.x} y={moon.y + visualMoon + 20 * unit} fontSize={13 * unit} className="body-label">Luna</text>
      {visible && ship && <>
        {velocity && arrow > 0 && <line x1={ship.x} y1={ship.y} x2={ship.x + velocity.x * arrow} y2={ship.y + velocity.y * arrow}
          stroke="#ffbd69" strokeWidth={1.7 * unit} markerEnd="url(#arrow-head)" />}
        <circle cx={ship.x} cy={ship.y} r={7 * unit} className="ship-sphere" fill={color} />
        {closeToShip && <image href="/resource/nave_espacial.svg" x={ship.x - shipIconSize / 2} y={ship.y - shipIconSize / 2}
          width={shipIconSize} height={shipIconSize} pointerEvents="none" />}
      </>}
    </svg>
    <div className="scene-heading scene-heading-local"><span className="eyebrow">SISTEMA TIERRA–LUNA</span><h1>{transfer ? 'Trayectoria calculada' : 'Acércate a la Luna'}</h1>
      <p>{transfer ? 'La nave sigue las muestras calculadas por el backend.' : 'Explora la vista lunar o configura una transferencia.'}</p></div>
    <div className="map-tools">
      <button className="icon-button" onClick={onSolar} aria-label="Volver al sistema solar" title="Volver al sistema solar"><Icon name="back" /></button>
      <button className="icon-button" onClick={() => zoom(.67)} aria-label="Acercar" title="Acercar"><Icon name="plus" /></button>
      <button className="icon-button" onClick={() => zoom(1.5)} aria-label="Alejar" title="Alejar"><Icon name="minus" /></button>
      <button className="icon-button" onClick={() => setBox(geometry.home)} aria-label="Encuadrar" title="Encuadrar"><Icon name="crosshair" /></button>
      <button className="icon-button" onClick={() => setBox({ x: moon.x - 20000, y: moon.y - 12800, w: 40000, h: 25600 })}
        aria-label="Enfocar Luna" title="Enfocar Luna"><Icon name="target" /></button>
    </div>
    <div className="view-legend">{transfer ? 'Plano Tierra–Luna real (km); iconos ampliados cuando es necesario' : 'Vista lunar ilustrativa; posiciones no obtenidas de JPL'} · Rueda para zoom · Arrastra para mover</div>
  </div>
}
