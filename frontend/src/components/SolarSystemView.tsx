import { useMemo, useRef, useState } from 'react'
import type { PointerEvent, WheelEvent } from 'react'
import { ORBIT_FLAT, PLANETS, SOLAR_CENTER, visualPlanetPosition } from '../data/solarSystem'
import { clamp } from '../utils/transfer'
import Icon from './Icon'

type Camera = { x: number; y: number; w: number; h: number }
type Props = { date: Date; journeyCount: number; onEarth: () => void }
const SIZE = { w: 1400, h: 790 }
const HOME: Camera = { x: 0, y: 0, w: SIZE.w, h: SIZE.h }
const stars = Array.from({ length: 240 }, (_, i) => ({
  x: (i * 763.71 + 113) % SIZE.w, y: (i * 443.29 + 57) % SIZE.h,
  r: i % 13 === 0 ? 1.2 : i % 5 === 0 ? .8 : .45,
  a: .2 + (i % 7) * .08,
}))

export default function SolarSystemView({ date, journeyCount, onEarth }: Props) {
  const [camera, setCamera] = useState<Camera>(HOME)
  const [focused, setFocused] = useState<string | null>(null)
  const svg = useRef<SVGSVGElement>(null)
  const drag = useRef<{ x: number; y: number; box: Camera; moved: boolean } | null>(null)
  const suppress = useRef(false)
  const planets = useMemo(() => PLANETS.map(p => ({ ...p, at: visualPlanetPosition(p, date) })), [date])
  const earth = planets.find(p => p.id === 'earth')!
  const unit = camera.w / SIZE.w

  function world(e: { clientX: number; clientY: number }) {
    if (!svg.current) return SOLAR_CENTER
    const matrix = svg.current.getScreenCTM()
    if (!matrix) return SOLAR_CENTER
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(matrix.inverse())
    return { x: p.x, y: p.y }
  }
  function zoom(factor: number, anchor: { x: number; y: number } = { x: camera.x + camera.w / 2, y: camera.y + camera.h / 2 }) {
    setCamera(old => {
      const w = clamp(old.w * factor, 85, 2500), ratio = w / old.w
      return { x: anchor.x - (anchor.x - old.x) * ratio, y: anchor.y - (anchor.y - old.y) * ratio, w, h: old.h * ratio }
    })
  }
  function wheel(e: WheelEvent<SVGSVGElement>) {
    e.preventDefault()
    const point = world(e)
    // Sólo una transición visual de escala; NO mezcla distancias científicas con radios ilustrativos.
    if (e.deltaY < 0 && camera.w < 280 && Math.hypot(point.x - earth.at.x, point.y - earth.at.y) < 65) {
      onEarth(); return
    }
    zoom(e.deltaY < 0 ? .82 : 1.22, point)
  }
  function pointerDown(e: PointerEvent<SVGSVGElement>) {
    if (e.button !== 0) return
    e.preventDefault()
    drag.current = { x: e.clientX, y: e.clientY, box: camera, moved: false }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  function pointerMove(e: PointerEvent<SVGSVGElement>) {
    if (!drag.current || !svg.current) return
    const d = drag.current, rect = svg.current.getBoundingClientRect()
    const s = Math.max(d.box.w / rect.width, d.box.h / rect.height)
    if (Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) > 5) d.moved = true
    setCamera({ ...d.box, x: d.box.x - (e.clientX - d.x) * s, y: d.box.y - (e.clientY - d.y) * s })
  }
  function pointerUp() {
    if (drag.current?.moved) {
      suppress.current = true
      window.setTimeout(() => { suppress.current = false }, 120)
    }
    drag.current = null
  }
  function selectPlanet(id: string) {
    if (suppress.current) { suppress.current = false; return }
    if (id === 'earth') { onEarth(); return }
    const p = planets.find(v => v.id === id)
    if (!p) return
    setFocused(id)
    const w = 420, h = w * SIZE.h / SIZE.w
    setCamera({ x: p.at.x - w / 2, y: p.at.y - h / 2, w, h })
  }

  return <div className="solar-view">
    <svg ref={svg} className="map-svg" viewBox={`${camera.x} ${camera.y} ${camera.w} ${camera.h}`}
      preserveAspectRatio="xMidYMid meet" role="img" aria-label="Sistema solar ilustrativo, con zoom y navegación"
      onWheel={wheel} onPointerDown={pointerDown} onPointerMove={pointerMove}
      onPointerUp={pointerUp} onPointerCancel={pointerUp} onLostPointerCapture={pointerUp}
      onDragStart={e => e.preventDefault()}>
      <defs>
        <radialGradient id="solar-sun-glow"><stop stopColor="#ffac4b" stopOpacity=".36" /><stop offset="1" stopColor="#ffac4b" stopOpacity="0" /></radialGradient>
      </defs>
      <rect x="-4000" y="-4000" width="9500" height="9500" fill="#071326" />
      {stars.map((s, i) => <circle key={i} cx={s.x} cy={s.y} r={s.r} opacity={s.a} fill="#b9d5ff" />)}
      {PLANETS.map(p => <ellipse key={p.id} cx={SOLAR_CENTER.x} cy={SOLAR_CENTER.y} rx={p.radius}
        ry={p.radius * ORBIT_FLAT} className="solar-orbit" />)}
      <circle cx={SOLAR_CENTER.x} cy={SOLAR_CENTER.y} r={95} fill="url(#solar-sun-glow)" />
      <image href="/resource/sol.svg" x={SOLAR_CENTER.x - 28} y={SOLAR_CENTER.y - 28} width="56" height="56" pointerEvents="none" />
      <text x={SOLAR_CENTER.x} y={SOLAR_CENTER.y + 46} className="planet-label" fontSize={13 * unit}>Sol</text>
      {planets.map(p => <g key={p.id} className="solar-body" onClick={() => selectPlanet(p.id)}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectPlanet(p.id) } }}
        role="button" tabIndex={0} aria-label={p.id === 'earth' ? 'Explorar Tierra y Luna' : `Enfocar ${p.name}`}>
        {focused === p.id && <circle cx={p.at.x} cy={p.at.y} r={p.size / 2 + 10} fill="none" stroke={p.color} strokeWidth={1.5 * unit} />}
        <circle cx={p.at.x} cy={p.at.y} r={Math.max(p.size / 2, 8 * unit)} fill={p.color} opacity=".3" />
        <image href={`/resource/${p.asset}`} x={p.at.x - p.size / 2} y={p.at.y - p.size / 2} width={p.size} height={p.size} pointerEvents="none" />
        <text x={p.at.x} y={p.at.y + p.size / 2 + 17 * unit} className="planet-label" fontSize={12 * unit}>{p.name}</text>
        {p.id === 'earth' && journeyCount > 0 && <g pointerEvents="none">
          <circle cx={p.at.x + 23} cy={p.at.y - 20} r={12 * unit} fill="#48d9ca" />
          <text x={p.at.x + 23} y={p.at.y - 16 * unit} textAnchor="middle" fontSize={11 * unit} fill="#071326" fontWeight="800">{journeyCount}</text>
        </g>}
      </g>)}
    </svg>
    <div className="scene-heading"><span className="eyebrow">EXPLORADOR ESPACIAL</span><h1>Explora el sistema solar</h1>
      <p>Acércate a la Tierra para descubrir el sistema Tierra–Luna.</p></div>
    <div className="map-tools">
      <button type="button" className="icon-button" title="Acercar" aria-label="Acercar" onClick={() => zoom(.66)}><Icon name="plus" /></button>
      <button type="button" className="icon-button" title="Alejar" aria-label="Alejar" onClick={() => zoom(1.5)}><Icon name="minus" /></button>
      <button type="button" className="icon-button" title="Centrar sistema solar" aria-label="Centrar sistema solar" onClick={() => { setCamera(HOME); setFocused(null) }}><Icon name="crosshair" /></button>
      <button type="button" className="icon-button accent-tool" title="Ver Tierra y Luna" aria-label="Ver Tierra y Luna" onClick={onEarth}><Icon name="globe" /></button>
    </div>
    <div className="view-legend solar-legend">Mapa ilustrativo, no a escala · Rueda para zoom · Arrastra para desplazarte · {Math.round(SIZE.w / camera.w * 10) / 10}×</div>
  </div>
}
