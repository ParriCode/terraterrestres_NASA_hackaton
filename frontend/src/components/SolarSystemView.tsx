import { useMemo, useRef, useState } from 'react'
import type { PointerEvent, WheelEvent } from 'react'
import { AU_M, PLANETS, planetOrbit, planetPosition } from '../data/solarSystem'
import type { TransferResponse, TransferState } from '../types/transfer'
import { eclipticToScreen, helioScreen, MKM } from '../utils/heliocentric'
import type { PointMkm } from '../utils/heliocentric'
import { clamp, findSampleInterval } from '../utils/transfer'
import Icon from './Icon'

/**
 * Vista "Sistema solar": marco heliocéntrico eclíptico J2000 a escala real de distancias
 * (unidad: millones de km). El Sol queda fijo en el origen. En una misión a Marte, la nave,
 * la Tierra y Marte salen de las muestras del backend (JPL Horizons) restando el Sol en cada
 * instante; el resto de planetas usa elementos orbitales medios de JPL.
 */
type Props = {
  date: Date; transfer: TransferResponse | null; state: TransferState | null
  visible?: boolean; color?: string; onEarth: () => void
}
type Box = { x: number; y: number; w: number; h: number }
const W = 1400, H = 790
const AU = AU_M / MKM
const f = (n: number) => n.toFixed(3)
const polyline = (points: PointMkm[]) => points.map(p => `${f(p.x)},${f(p.y)}`).join(' ')

/** Encuadre centrado en el Sol. Margen vertical mayor: arriba está el selector de vista y
 * abajo la línea de tiempo, que tapan ~15 % de la altura cada uno. */
function frame(points: PointMkm[], margin = 1.08): Box {
  const half = Math.max(...points.map(p => Math.max(Math.abs(p.x) * margin, Math.abs(p.y) * W / H * margin * 1.25)))
  const w = 2 * half, h = w * H / W
  return { x: -half, y: -h / 2, w, h }
}

export default function SolarSystemView({ date, transfer, state, visible = true, color = '#70efd8', onEarth }: Props) {
  const svg = useRef<SVGSVGElement>(null)
  const drag = useRef<{ x: number; y: number; box: Box; moved: boolean } | null>(null)
  const suppressClick = useRef(false)
  const isMars = transfer?.destination === 'mars'
  const basis = transfer?.basis_icrf

  // Órbitas completas: basta recalcularlas una vez por día (cambian siglos a siglos).
  const orbitDay = date.toISOString().slice(0, 10)
  const orbits = useMemo(() => {
    const day = new Date(`${orbitDay}T00:00:00Z`)
    return PLANETS.map(p => ({ id: p.id, points: polyline(planetOrbit(p, day).map(eclipticToScreen)) }))
  }, [orbitDay])

  // Trayectoria heliocéntrica de la misión a Marte (Sol restado muestra a muestra).
  const mission = useMemo(() => {
    if (!transfer || !isMars || !basis || !transfer.samples.every(s => s.body_positions_m.sun && s.body_positions_m.mars)) return null
    const s = transfer.samples
    const ship = s.map(x => helioScreen(x.position_m, x.body_positions_m.sun!, basis))
    const earth = s.map(x => helioScreen(x.body_positions_m.earth, x.body_positions_m.sun!, basis))
    const mars = s.map(x => helioScreen(x.body_positions_m.mars!, x.body_positions_m.sun!, basis))
    return { ship, earth, mars, earthTrack: polyline(earth), marsTrack: polyline(mars) }
  }, [transfer, isMars, basis])

  const home = useMemo(() => {
    const marsOrbit = planetOrbit(PLANETS[3], new Date(`${orbitDay}T00:00:00Z`)).map(eclipticToScreen)
    return frame(mission ? [...marsOrbit, ...mission.ship] : marsOrbit)
  }, [mission, orbitDay])
  const outer = useMemo(() => frame(planetOrbit(PLANETS[7], new Date(`${orbitDay}T00:00:00Z`)).map(eclipticToScreen), 1.06), [orbitDay])

  const [view, setView] = useState<{ key: TransferResponse | null; box: Box }>({ key: transfer, box: home })
  const box = view.key === transfer ? view.box : home
  const setBox = (next: Box) => setView({ key: transfer, box: next })
  const unit = box.w / W
  // Los estilos CSS de etiquetas usan px de usuario; aquí la unidad es 1 M km, así que se escalan.
  const lbl = (px: number) => ({ fontSize: px * unit, strokeWidth: 3 * unit })

  // Posiciones en el instante actual.
  const helioNow = (p?: readonly number[]) => p && state?.sun_m && basis ? helioScreen(p, state.sun_m, basis) : null
  const shipNow = isMars ? helioNow(state?.position_m) : null
  const bodies = PLANETS.map(p => {
    const jpl = isMars ? (p.id === 'earth' ? helioNow(state?.earth_m) : p.id === 'mars' ? helioNow(state?.mars_m) : null) : null
    return { ...p, at: jpl ?? eclipticToScreen(planetPosition(p, date)) }
  })
  const earthNow = bodies[2].at, marsNow = bodies[3].at

  const split = mission && transfer && shipNow ? findSampleInterval(transfer.samples, state?.t_s ?? 0) + 1 : 0
  const segments = mission && shipNow
    ? { past: polyline([...mission.ship.slice(0, split), shipNow]), future: polyline([shipNow, ...mission.ship.slice(split)]) }
    : { past: '', future: '' }

  function toWorld(e: { clientX: number; clientY: number }) {
    const matrix = svg.current?.getScreenCTM()
    if (!matrix) return { x: box.x + box.w / 2, y: box.y + box.h / 2 }
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(matrix.inverse())
    return { x: p.x, y: p.y }
  }
  function zoom(factor: number, anchor = { x: box.x + box.w / 2, y: box.y + box.h / 2 }) {
    const w = clamp(box.w * factor, 3, outer.w * 1.6), ratio = w / box.w
    setBox({ x: anchor.x - (anchor.x - box.x) * ratio, y: anchor.y - (anchor.y - box.y) * ratio, w, h: box.h * ratio })
  }
  function focus(p: PointMkm, w = 60) { setBox({ x: p.x - w / 2, y: p.y - w * H / W / 2, w, h: w * H / W }) }
  function pointerDown(e: PointerEvent<SVGSVGElement>) {
    if (e.button !== 0) return
    drag.current = { x: e.clientX, y: e.clientY, box, moved: false }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  function pointerMove(e: PointerEvent<SVGSVGElement>) {
    if (!drag.current || !svg.current) return
    const d = drag.current, rect = svg.current.getBoundingClientRect()
    const s = Math.max(d.box.w / rect.width, d.box.h / rect.height)
    if (Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) > 4) d.moved = true
    if (d.moved) setBox({ ...d.box, x: d.box.x - (e.clientX - d.x) * s, y: d.box.y - (e.clientY - d.y) * s })
  }
  function pointerUp() {
    if (drag.current?.moved) { suppressClick.current = true; window.setTimeout(() => { suppressClick.current = false }, 80) }
    drag.current = null
  }
  function selectBody(id: string, at: PointMkm) {
    if (suppressClick.current) return
    if (id === 'earth') onEarth()
    else focus(at, id === 'mars' ? 60 : Math.max(60, Math.hypot(at.x, at.y) * 0.5))
  }

  const days = transfer ? transfer.duration_s / 86400 : 0
  // Barra de escala 1-2-5 que no ocupe más del 18 % del ancho visible.
  const scaleAu = [20, 10, 5, 2, 1, 0.5, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001].find(v => v * AU <= box.w * 0.18) ?? 0.001
  const scaleLen = scaleAu * AU
  const start = mission?.ship[0], end = mission?.ship[mission.ship.length - 1]
  // Marcadores fantasma solo cuando el planeta ya no está en ese punto (evita etiquetas duplicadas).
  const tNow = state?.t_s ?? 0, ghostGap = 12 * 86400
  const marsAtDeparture = tNow > ghostGap ? mission?.mars[0] : undefined
  const earthAtArrival = transfer && tNow < transfer.duration_s - ghostGap ? mission?.earth[mission.earth.length - 1] : undefined

  return <div className="solar-view">
    <svg ref={svg} className="map-svg" viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`} preserveAspectRatio="xMidYMid meet"
      role="img" aria-label="Sistema solar en marco heliocéntrico, con el Sol en el centro"
      onWheel={(e: WheelEvent<SVGSVGElement>) => { e.preventDefault(); zoom(e.deltaY < 0 ? .82 : 1.22, toWorld(e)) }}
      onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp}
      onPointerCancel={pointerUp} onLostPointerCapture={pointerUp} onDragStart={e => e.preventDefault()}>
      <defs><radialGradient id="solar-sun-glow"><stop stopColor="#ffac4b" stopOpacity=".42" /><stop offset="1" stopColor="#ffac4b" stopOpacity="0" /></radialGradient></defs>

      {orbits.map(o => <polyline key={o.id} points={o.points} className="solar-orbit" style={{
        strokeWidth: (o.id === 'earth' || o.id === 'mars' ? 1.4 : 1) * unit, strokeDasharray: `${4 * unit} ${5 * unit}`,
        ...(o.id === 'earth' ? { stroke: '#3f7fae', opacity: .9 } : o.id === 'mars' ? { stroke: '#a0624c', opacity: .9 } : {}),
      }} />)}

      {mission && <>
        <polyline points={mission.earthTrack} fill="none" stroke="#66c8ff" strokeWidth={3 * unit} opacity={.45} strokeLinecap="round" />
        <polyline points={mission.marsTrack} fill="none" stroke="#ea9773" strokeWidth={3 * unit} opacity={.45} strokeLinecap="round" />
        {visible && <>
          <polyline points={segments.future} fill="none" stroke={color} strokeWidth={2 * unit} strokeDasharray={`${7 * unit} ${7 * unit}`} opacity={.75} />
          <polyline points={segments.past} fill="none" stroke={color} strokeWidth={3 * unit} strokeLinecap="round" />
        </>}
        {marsAtDeparture && <g opacity={.6}>
          <circle cx={marsAtDeparture.x} cy={marsAtDeparture.y} r={6 * unit} fill="none" stroke="#ea9773" strokeWidth={1.5 * unit} strokeDasharray={`${2 * unit} ${2 * unit}`} />
          <text x={marsAtDeparture.x} y={marsAtDeparture.y - 12 * unit} className="planet-label" style={lbl(10)}>Marte al salir</text>
        </g>}
        {earthAtArrival && <g opacity={.6}>
          <circle cx={earthAtArrival.x} cy={earthAtArrival.y} r={6 * unit} fill="none" stroke="#66c8ff" strokeWidth={1.5 * unit} strokeDasharray={`${2 * unit} ${2 * unit}`} />
          <text x={earthAtArrival.x} y={earthAtArrival.y - 12 * unit} className="planet-label" style={lbl(10)}>Tierra a la llegada</text>
        </g>}
        {visible && start && <g>
          <circle cx={start.x} cy={start.y} r={5 * unit} fill="#64ead5" stroke="#071326" strokeWidth={1.5 * unit} />
          <text x={start.x - 12 * unit} y={start.y - 14 * unit} className="planet-label" style={{ ...lbl(11), textAnchor: 'end' }}>Salida (TMI)</text>
        </g>}
        {visible && end && <g>
          <circle cx={end.x} cy={end.y} r={5 * unit} fill="#ffb56b" stroke="#071326" strokeWidth={1.5 * unit}>
            <title>Inserción en órbita de Marte (MOI) en el periapsis</title></circle>
          <text x={end.x + 14 * unit} y={end.y + 4 * unit} className="planet-label" style={{ ...lbl(11), textAnchor: 'start' }}>Llegada (MOI) · {Math.round(days)} d</text>
        </g>}
      </>}

      <circle cx={0} cy={0} r={60 * unit} fill="url(#solar-sun-glow)" />
      <image href="/resource/sol.svg" x={-17 * unit} y={-17 * unit} width={34 * unit} height={34 * unit} pointerEvents="none" />
      <text x={0} y={32 * unit} className="planet-label" style={lbl(12)}>Sol</text>

      {bodies.map(p => <g key={p.id} className="solar-body" role="button" tabIndex={0}
        aria-label={p.id === 'earth' ? 'Ver sistema Tierra–Luna' : `Enfocar ${p.name}`}
        onClick={() => selectBody(p.id, p.at)}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectBody(p.id, p.at) } }}>
        <circle cx={p.at.x} cy={p.at.y} r={(p.size / 2 + 5) * unit} fill={p.color} opacity={.22} />
        <image href={`/resource/${p.asset}`} x={p.at.x - p.size / 2 * unit} y={p.at.y - p.size / 2 * unit}
          width={p.size * unit} height={p.size * unit} pointerEvents="none" />
        <text x={p.at.x} y={p.at.y + (p.size / 2 + 15) * unit} className="planet-label" style={lbl(12)}>{p.name}</text>
        {p.id === 'earth' && transfer && !isMars && <text x={p.at.x} y={p.at.y - (p.size / 2 + 9) * unit}
          className="planet-label" style={{ ...lbl(10), fill: '#83f8df' }}>misión lunar aquí</text>}
      </g>)}

      {visible && shipNow && <g pointerEvents="none">
        <circle cx={shipNow.x} cy={shipNow.y} r={5 * unit} fill={color} stroke="#071326" strokeWidth={1.5 * unit} />
        <image href="/resource/nave_espacial.svg" x={shipNow.x - 11 * unit} y={shipNow.y - 26 * unit} width={22 * unit} height={22 * unit} />
      </g>}

      <g pointerEvents="none" transform={`translate(${box.x + 24 * unit} ${box.y + box.h - 46 * unit})`}>
        <line x1={0} y1={0} x2={scaleLen} y2={0} stroke="#c9d8ea" strokeWidth={2 * unit} />
        <line x1={0} y1={-5 * unit} x2={0} y2={5 * unit} stroke="#c9d8ea" strokeWidth={2 * unit} />
        <line x1={scaleLen} y1={-5 * unit} x2={scaleLen} y2={5 * unit} stroke="#c9d8ea" strokeWidth={2 * unit} />
        <text x={scaleLen / 2} y={-9 * unit} className="planet-label" style={lbl(11)}>{scaleAu.toLocaleString('es-ES')} UA ≈ {scaleLen.toLocaleString('es-ES', { maximumSignificantDigits: 3 })} M km</text>
      </g>
    </svg>

    <div className="scene-heading scene-heading-local"><span className="eyebrow">SISTEMA SOLAR · HELIOCÉNTRICO</span>
      <h1>{isMars ? 'Tierra → Marte · solo ida' : transfer ? 'Misión lunar · vista solar' : 'Sistema solar'}</h1>
      <p>{isMars
        ? `Trayectoria del backend con el Sol fijo en el centro: ${Math.round(days)} días de crucero. Los arcos gruesos son el movimiento de la Tierra y Marte durante el viaje.`
        : transfer ? 'Una misión lunar no se aleja más de ~0,003 UA de la Tierra: ábrela en la vista Tierra–Luna para ver la trayectoria.'
          : 'Posiciones de los planetas en la fecha elegida. Pulsa la Tierra para ver el sistema Tierra–Luna.'}</p></div>

    <div className="map-tools">
      <button type="button" className="icon-button" onClick={() => zoom(.67)} aria-label="Acercar" title="Acercar"><Icon name="plus" /></button>
      <button type="button" className="icon-button" onClick={() => zoom(1.5)} aria-label="Alejar" title="Alejar"><Icon name="minus" /></button>
      <button type="button" className="icon-button" onClick={() => setBox(home)} aria-label="Encuadrar sistema solar interior" title="Encuadrar sistema solar interior"><Icon name="crosshair" /></button>
      <button type="button" className="icon-button" onClick={() => setBox(outer)} aria-label="Ver sistema solar completo" title="Ver sistema solar completo"><Icon name="orbit" /></button>
      <button type="button" className="icon-button" onClick={() => focus(marsNow)} aria-label="Enfocar Marte" title="Enfocar Marte"><Icon name="target" /></button>
      <button type="button" className="icon-button accent-tool" onClick={() => focus(earthNow, 20)} onDoubleClick={onEarth} aria-label="Enfocar la Tierra" title="Enfocar la Tierra (doble clic: vista Tierra–Luna)"><Icon name="globe" /></button>
    </div>
    <div className="view-legend">Eclíptica J2000 heliocéntrica · distancias a escala, iconos ampliados · Rueda para zoom · Arrastra para mover</div>
  </div>
}
