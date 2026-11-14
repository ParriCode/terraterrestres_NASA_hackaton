import { useMemo, useRef, useState } from 'react'
import type { PointerEvent, WheelEvent } from 'react'
import type { TransferResponse, TransferSample, TransferState } from '../types/transfer'
import { clamp } from '../utils/transfer'
import Icon from './Icon'

type Props = { transfer: TransferResponse; state: TransferState }
type Box = { x: number; y: number; w: number; h: number }

const W = 1000, H = 640
// Coordenadas en km; Y invertida porque en SVG crece hacia abajo
const toKm = (v: readonly number[]) => ({ x: v[0] / 1000, y: -v[1] / 1000 })
const polyline = (points: { x: number; y: number }[]) => points.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')

/** Curva de la nave: cada tramo es la Bézier cúbica equivalente al Hermite con las velocidades del backend. */
function shipPath(samples: TransferSample[]) {
  const f = (n: number) => n.toFixed(2)
  let d = `M${f(samples[0].position_m[0] / 1000)},${f(-samples[0].position_m[1] / 1000)}`
  for (let i = 1; i < samples.length; i++) {
    const a = samples[i - 1], b = samples[i], k = (b.t_s - a.t_s) / 3000 // h/3, en km
    d += `C${f(a.position_m[0] / 1000 + a.velocity_m_s[0] * k)},${f(-(a.position_m[1] / 1000 + a.velocity_m_s[1] * k))}`
      + ` ${f(b.position_m[0] / 1000 - b.velocity_m_s[0] * k)},${f(-(b.position_m[1] / 1000 - b.velocity_m_s[1] * k))}`
      + ` ${f(b.position_m[0] / 1000)},${f(-b.position_m[1] / 1000)}`
  }
  return d
}

/** Vista 2D en el plano baricéntrico del backend, a escala real (km). */
export default function TransferView({ transfer, state }: Props) {
  const svg = useRef<SVGSVGElement>(null)
  const drag = useRef<{ x: number; y: number; box: Box } | null>(null)

  const geometry = useMemo(() => {
    const ship = transfer.samples.map(s => toKm(s.position_m))
    const earth = transfer.samples.map(s => toKm(s.body_positions_m.earth))
    const moon = transfer.samples.map(s => toKm(s.body_positions_m.moon))
    const all = [...ship, ...earth, ...moon]
    const pad = 30_000
    const minX = Math.min(...all.map(p => p.x)) - pad, maxX = Math.max(...all.map(p => p.x)) + pad
    const minY = Math.min(...all.map(p => p.y)) - pad, maxY = Math.max(...all.map(p => p.y)) + pad
    // Encaja el contenido manteniendo la proporción del lienzo
    const scale = Math.max((maxX - minX) / W, (maxY - minY) / H)
    const w = W * scale, h = H * scale
    const home: Box = { x: (minX + maxX - w) / 2, y: (minY + maxY - h) / 2, w, h }
    return { ship: shipPath(transfer.samples), earth: polyline(earth), moon: polyline(moon), home }
  }, [transfer])

  const [view, setView] = useState<{ key: TransferResponse; box: Box }>({ key: transfer, box: geometry.home })
  const box = view.key === transfer ? view.box : geometry.home // nueva transferencia → encuadre inicial
  const setBox = (b: Box) => setView({ key: transfer, box: b })
  const unit = box.w / W // km por píxel de pantalla

  function toWorld(e: { clientX: number; clientY: number }) {
    const rect = svg.current!.getBoundingClientRect()
    const s = Math.max(box.w / rect.width, box.h / rect.height)
    const ox = (rect.width * s - box.w) / 2, oy = (rect.height * s - box.h) / 2
    return { x: box.x - ox + (e.clientX - rect.left) * s, y: box.y - oy + (e.clientY - rect.top) * s }
  }
  function zoom(factor: number, anchor = { x: box.x + box.w / 2, y: box.y + box.h / 2 }) {
    const w = clamp(box.w * factor, 2000, geometry.home.w * 4)
    const f = w / box.w
    setBox({ x: anchor.x - (anchor.x - box.x) * f, y: anchor.y - (anchor.y - box.y) * f, w, h: box.h * f })
  }
  const onWheel = (e: WheelEvent<SVGSVGElement>) => zoom(e.deltaY < 0 ? 1 / 1.2 : 1.2, toWorld(e))
  function onPointerDown(e: PointerEvent<SVGSVGElement>) {
    if (e.button !== 0) return
    drag.current = { x: e.clientX, y: e.clientY, box }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  function onPointerMove(e: PointerEvent<SVGSVGElement>) {
    if (!drag.current) return
    const rect = svg.current!.getBoundingClientRect()
    const b = drag.current.box
    const s = Math.max(b.w / rect.width, b.h / rect.height)
    setBox({ ...b, x: b.x - (e.clientX - drag.current.x) * s, y: b.y - (e.clientY - drag.current.y) * s })
  }

  const earth = toKm(state.earth_m), moon = toKm(state.moon_m), ship = toKm(state.position_m)
  const rEarth = transfer.bodies.earth.radius_m / 1000, rMoon = transfer.bodies.moon.radius_m / 1000
  // Velocidad: flecha proporcional, longitud fija en pantalla para la referencia de 1 km/s
  const v = toKm(state.velocity_m_s), speed = Math.hypot(v.x, v.y)
  const arrow = speed > 0 ? 60 * unit * Math.min(3, speed) / speed : 0

  return <div className="transfer-view">
    <svg ref={svg} viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`} preserveAspectRatio="xMidYMid meet"
      onWheel={onWheel} onPointerDown={onPointerDown} onPointerMove={onPointerMove}
      onPointerUp={() => { drag.current = null }} onPointerCancel={() => { drag.current = null }}
      role="img" aria-label="Trayectoria de la transferencia Tierra–Luna en el plano baricéntrico">
      <defs>
        <marker id="arrow-head" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="#ffbd69" />
        </marker>
      </defs>
      <circle cx="0" cy="0" r={4 * unit} fill="#90a1bb" opacity=".7"><title>Baricentro Tierra–Luna</title></circle>
      <polyline points={geometry.earth} className="body-track earth-track" strokeWidth={1.2 * unit} />
      <polyline points={geometry.moon} className="body-track moon-track" strokeWidth={1.2 * unit} strokeDasharray={`${6 * unit} ${6 * unit}`} />
      <path d={geometry.ship} className="ship-track" strokeWidth={2.2 * unit} />

      <circle cx={earth.x} cy={earth.y} r={Math.max(rEarth, 3 * unit)} className="earth-glow" />
      <image href="/resource/tierra.svg" x={earth.x - rEarth * 1.45} y={earth.y - rEarth * 1.45} width={rEarth * 2.9} height={rEarth * 2.9} />
      <circle cx={earth.x} cy={earth.y} r={rEarth} fill="none" stroke="#64d9ff" strokeWidth={unit} />
      <text x={earth.x} y={earth.y + rEarth + 18 * unit} fontSize={13 * unit} className="body-label">Tierra</text>

      <image href="/resource/luna.svg" x={moon.x - rMoon * 1.255} y={moon.y - rMoon * 1.255} width={rMoon * 2.51} height={rMoon * 2.51} />
      <circle cx={moon.x} cy={moon.y} r={Math.max(rMoon, 2 * unit)} fill="none" stroke="#d8dbe2" strokeWidth={unit} />
      <text x={moon.x} y={moon.y + Math.max(rMoon, 2 * unit) + 18 * unit} fontSize={13 * unit} className="body-label">Luna</text>

      {arrow > 0 && <line x1={ship.x} y1={ship.y} x2={ship.x + v.x * arrow} y2={ship.y + v.y * arrow}
        stroke="#ffbd69" strokeWidth={1.6 * unit} markerEnd="url(#arrow-head)" />}
      <circle cx={ship.x} cy={ship.y} r={6 * unit} className="ship-sphere"><title>Nave</title></circle>
    </svg>
    <div className="view-toolbar">
      <button className="icon-button" onClick={() => zoom(1 / 1.5)} aria-label="Acercar" title="Acercar"><Icon name="plus" /></button>
      <button className="icon-button" onClick={() => zoom(1.5)} aria-label="Alejar" title="Alejar"><Icon name="minus" /></button>
      <button className="icon-button" onClick={() => setBox(geometry.home)} aria-label="Encuadrar" title="Encuadrar"><Icon name="crosshair" /></button>
      <button className="icon-button" onClick={() => setBox({ x: moon.x - 15_000, y: moon.y - 9_600, w: 30_000, h: 19_200 })} aria-label="Ver llegada a la Luna" title="Ver llegada a la Luna"><Icon name="target" /></button>
    </div>
    <div className="view-legend">Plano baricéntrico Tierra–Luna · +X = equinoccio vernal · escala real · rueda para zoom, arrastra para mover</div>
  </div>
}
