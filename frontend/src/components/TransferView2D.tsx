import { useMemo, useRef, useState } from 'react'
import type { PointerEvent, WheelEvent } from 'react'
import type { TransferResponse, TransferSample, TransferState } from '../types/transfer'
import { clamp, stateAt } from '../utils/transfer'
import Icon from './Icon'
import type { EarthMoonEphemeris, SunDirectionEphemeris } from '../api/ephemerides'
import { projectIcrfKm } from '../utils/icrfProjection'

type Props = { date: Date; transfer: TransferResponse | null; state: TransferState | null; time: number; visible?: boolean; color?: string
  preview: EarthMoonEphemeris | null; previewError: string; sun: SunDirectionEphemeris | null; sunError: string }
type Box = { x: number; y: number; w: number; h: number }
type Point = { x: number; y: number }
const W = 1000, H = 640
const PREVIEW: Box = { x: -104000, y: -187000, w: 590000, h: 377600 }
const f = (n: number) => n.toFixed(2)
const polyline = (points: Point[]) => points.map(p => `${f(p.x)},${f(p.y)}`).join(' ')

/** Curva Hermite visual. Los puntos y velocidades provienen EXCLUSIVAMENTE del backend. */
function makePath(samples: TransferSample[], basis: number[][]): string {
  if (!samples.length) return ''
  const start = projectIcrfKm(samples[0].position_m, basis)
  let d = `M${f(start.x)},${f(start.y)}`
  for (let i = 1; i < samples.length; i++) {
    const a = samples[i - 1], b = samples[i]
    const p0 = projectIcrfKm(a.position_m, basis)
    const p1 = projectIcrfKm(b.position_m, basis)
    const v0 = projectIcrfKm(a.velocity_m_s, basis)
    const v1 = projectIcrfKm(b.velocity_m_s, basis)
    const dtThird = (b.t_s - a.t_s) / 3
    d += ` C${f(p0.x + v0.x * dtThird)},${f(p0.y + v0.y * dtThird)}`
      + ` ${f(p1.x - v1.x * dtThird)},${f(p1.y - v1.y * dtThird)}`
      + ` ${f(p1.x)},${f(p1.y)}`
  }
  return d
}

export default function TransferView2D({ transfer, state, time, preview, previewError, sun, sunError, visible = true, color = '#70efd8' }: Props) {
  const svg = useRef<SVGSVGElement>(null)
  const drag = useRef<{ x: number; y: number; box: Box } | null>(null)
  // En 2D la flecha conserva la proyección ICRF XY original.
  const solarXY = sun ? { x: sun.direction_icrf[0], y: -sun.direction_icrf[1] } : null
  const solarAngleDeg = solarXY && Math.hypot(solarXY.x, solarXY.y) > 1e-6
    ? Math.atan2(solarXY.y, solarXY.x) * 180 / Math.PI : null
  const geometry = useMemo(() => {
    const basis = transfer?.basis_icrf
    const all = transfer ? [
      ...transfer.samples.map(s => projectIcrfKm(s.position_m, basis)),
      ...transfer.samples.map(s => projectIcrfKm(s.body_positions_m.earth, basis)),
      ...transfer.samples.map(s => projectIcrfKm(s.body_positions_m.moon, basis)),
    ] : preview ? [
      projectIcrfKm(preview.body_positions_m.earth),
      projectIcrfKm(preview.body_positions_m.moon),
    ] : []
    if (!all.length) return { earth: '', moon: '', home: PREVIEW }
    const earth = transfer ? transfer.samples.map(s => projectIcrfKm(s.body_positions_m.earth, basis)) : []
    const moon = transfer ? transfer.samples.map(s => projectIcrfKm(s.body_positions_m.moon, basis)) : []
    const pad = 35000
    const minX = Math.min(...all.map(p => p.x)) - pad, maxX = Math.max(...all.map(p => p.x)) + pad
    const minY = Math.min(...all.map(p => p.y)) - pad, maxY = Math.max(...all.map(p => p.y)) + pad
    const scale = Math.max((maxX - minX) / W, (maxY - minY) / H)
    const w = W * scale, h = H * scale
    return { earth: polyline(earth), moon: polyline(moon), home: { x: (minX + maxX - w) / 2, y: (minY + maxY - h) / 2, w, h } }
  }, [transfer, preview])
  const viewKey = transfer ?? preview
  const [view, setView] = useState<{ key: TransferResponse | EarthMoonEphemeris | null; box: Box }>({ key: viewKey, box: geometry.home })
  const box = view.key === viewKey ? view.box : geometry.home
  const setBox = (next: Box) => setView({ key: viewKey, box: next })
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
    return { past: makePath([...past, now], transfer.basis_icrf), future: makePath([now, ...future], transfer.basis_icrf) }
  }, [transfer, state, time])

  const earthEntry = transfer?.earth_entry?.validated && transfer.samples.length
    ? projectIcrfKm(transfer.samples[transfer.samples.length - 1].position_m, transfer.basis_icrf)
    : null

  const maneuverPoints = transfer?.maneuvers?.map(m => ({
    phase: m.phase, position: projectIcrfKm(stateAt(transfer.samples, m.t_s).position_m, transfer.basis_icrf),
  })) ?? []

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

  // Misma orientación inercial ICRF en todas las fechas. Sin coordenadas JPL, sin Luna inventada.
  const earth = state ? projectIcrfKm(state.earth_m, transfer?.basis_icrf)
    : preview ? projectIcrfKm(preview.body_positions_m.earth) : null
  const moon = state ? projectIcrfKm(state.moon_m, transfer?.basis_icrf)
    : preview ? projectIcrfKm(preview.body_positions_m.moon) : null
  const ship = state ? projectIcrfKm(state.position_m, transfer?.basis_icrf) : null
  const rEarth = (transfer?.bodies.earth.radius_m ?? 6371000) / 1000
  const rMoon = (transfer?.bodies.moon.radius_m ?? 1737400) / 1000
  const visualEarth = Math.max(rEarth, 21 * unit)
  const visualMoon = Math.max(rMoon, 13 * unit)
  const shipIconSize = 26 * unit
  const closeToShip = box.w < 130000
  const velocity = state ? projectIcrfKm(state.velocity_m_s, transfer?.basis_icrf) : null
  const speed = velocity ? Math.hypot(velocity.x, velocity.y) : 0
  const arrow = speed > 0 ? 55 * unit * Math.min(3, speed) / speed : 0

  return <div className="transfer-view">
    <svg ref={svg} className="map-svg" viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`} preserveAspectRatio="xMidYMid meet"
      onWheel={(e: WheelEvent<SVGSVGElement>) => { e.preventDefault(); zoom(e.deltaY < 0 ? .83 : 1.2, toWorld(e)) }}
      onPointerDown={pointerDown} onPointerMove={pointerMove}
      onPointerUp={() => { drag.current = null }} onPointerCancel={() => { drag.current = null }}
      onLostPointerCapture={() => { drag.current = null }} onDragStart={e => e.preventDefault()}
      role="img" aria-label={transfer ? 'Trayectoria de la nave en proyección ICRF del sistema Tierra–Luna' : 'Posiciones Tierra y Luna consultadas a NASA/JPL cuando están disponibles'}>
      <defs><marker id="arrow-head" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" fill="#ffbd69" /></marker></defs>

      {transfer && <>
        <polyline points={geometry.earth} className="body-track earth-track" strokeWidth={1.2 * unit} />
        <polyline points={geometry.moon} className="body-track moon-track" strokeWidth={1.2 * unit} strokeDasharray={`${6 * unit} ${6 * unit}`} />
        {visible && <>
          <path d={segments.future} className="ship-track ship-track-future" stroke={color} strokeWidth={2.4 * unit} strokeDasharray={`${7 * unit} ${9 * unit}`} />
          <path d={segments.past} className="ship-track ship-track-past" stroke={color} strokeWidth={3.2 * unit} />
        </>}
      </>}
      {visible && maneuverPoints.map(point => <g key={point.phase}>
        <circle cx={point.position.x} cy={point.position.y} r={6 * unit} fill="#ffb56b" stroke="#141825" strokeWidth={2 * unit}>
          <title>{point.phase === 'inserción_orbital' ? 'Inserción en órbita lunar' : 'Maniobra de retorno a la Tierra'}</title>
        </circle>
        {box.w < 90000 && <text x={point.position.x + 10 * unit} y={point.position.y - 10 * unit}
          fontSize={12 * unit} className="body-label">{point.phase === 'inserción_orbital' ? 'Inserción orbital' : 'Salida de órbita'}</text>}
      </g>)}
      {earth && <>
        <circle cx={earth.x} cy={earth.y} r={visualEarth * 1.2} className="earth-glow" />
        <image href="/resource/tierra.svg" x={earth.x - visualEarth} y={earth.y - visualEarth} width={visualEarth * 2} height={visualEarth * 2} />
        <circle cx={earth.x} cy={earth.y} r={rEarth} fill="none" stroke="#64d9ff" strokeWidth={1.3 * unit} />
        <text x={earth.x} y={earth.y + visualEarth + 20 * unit} fontSize={13 * unit} className="body-label">Tierra</text>
      </>}
      {moon && <>
        <image href="/resource/luna.svg" x={moon.x - visualMoon} y={moon.y - visualMoon} width={visualMoon * 2} height={visualMoon * 2} />
        <circle cx={moon.x} cy={moon.y} r={rMoon} fill="none" stroke="#dadce5" strokeWidth={1.2 * unit} />
        <text x={moon.x} y={moon.y + visualMoon + 20 * unit} fontSize={13 * unit} className="body-label">Luna</text>
      </>}
      {visible && earthEntry && <g>
        <circle cx={earthEntry.x} cy={earthEntry.y} r={8 * unit} fill="#68f1ba" stroke="#071523" strokeWidth={2 * unit}>
          <title>Llegada a la Tierra: interfaz atmosférica a 120 km de altitud (sin aterrizaje simulado)</title>
        </circle>
        {box.w < 130000 && <text x={earthEntry.x + 12 * unit} y={earthEntry.y - 12 * unit}
          className="body-label" fontSize={12 * unit}>Llegada a la Tierra</text>}
      </g>}
      {visible && ship && <>
        {velocity && arrow > 0 && <line x1={ship.x} y1={ship.y} x2={ship.x + velocity.x * arrow} y2={ship.y + velocity.y * arrow}
          stroke="#ffbd69" strokeWidth={1.7 * unit} markerEnd="url(#arrow-head)" />}
        <circle cx={ship.x} cy={ship.y} r={7 * unit} className="ship-sphere" fill={color} />
        {closeToShip && <image href="/resource/nave_espacial.svg" x={ship.x - shipIconSize / 2} y={ship.y - shipIconSize / 2}
          width={shipIconSize} height={shipIconSize} pointerEvents="none" />}
      </>}
    </svg>
    <div className="scene-heading scene-heading-local"><span className="eyebrow">SISTEMA TIERRA–LUNA <span className="space-dimension">VISOR 2D</span></span><h1>{transfer?.mission_mode === 'lunar_orbit_return' ? 'Apolo 11 · Órbita lunar y regreso' : transfer?.mission_mode === 'free_return' ? 'Apolo 8/13 · Retorno libre' : transfer ? 'Trayectoria calculada' : preview ? 'Posición lunar según JPL' : previewError ? 'Efemérides no disponibles' : 'Consultando NASA/JPL…'}</h1>
      <p>{transfer ? 'La nave sigue las muestras calculadas por el backend.' : previewError || (preview ? `Fecha UTC: ${new Date(preview.date).toLocaleString('es-ES', { timeZone: 'UTC' })}` : 'Descargando las posiciones reales para la fecha seleccionada.')}</p></div>
    <div className="sun-indicator"
      title={sun ? `Dirección Tierra → Sol calculada con JPL Horizons (${sun.date}). Proyección XY; el Sol está fuera de escala.` : sunError || 'Consultando la dirección solar en JPL Horizons'}>
      <img src="/resource/sol.svg" alt="" draggable={false} />
      <span>Sol</span>
      {solarAngleDeg !== null
        ? <span className="sun-indicator__arrow" style={{ transform: `rotate(${solarAngleDeg}deg)` }}>
            <Icon name="arrow" size={17} />
          </span>
        : <span className="sun-indicator__unavailable" aria-label="Dirección solar no disponible">{sunError ? 'Sin datos' : '…'}</span>}
    </div>
    <div className="map-tools">
      <button className="icon-button" onClick={() => zoom(.67)} aria-label="Acercar" title="Acercar"><Icon name="plus" /></button>
      <button className="icon-button" onClick={() => zoom(1.5)} aria-label="Alejar" title="Alejar"><Icon name="minus" /></button>
      <button className="icon-button" onClick={() => setBox(geometry.home)} aria-label="Encuadrar" title="Encuadrar"><Icon name="crosshair" /></button>
      <button className="icon-button" disabled={!moon} onClick={() => { if (moon) setBox({ x: moon.x - 20000, y: moon.y - 12800, w: 40000, h: 25600 }) }}
        aria-label="Enfocar Luna" title="Enfocar Luna"><Icon name="target" /></button>
    </div>
    <div className="view-legend">{transfer ? 'Tierra–Luna: efemérides JPL, proyección ICRF XY (km); trayectorias 3D proyectadas; iconos ampliados' : preview ? 'Posiciones JPL Horizons: proyección ICRF XY (km); iconos ampliados' : 'Sin posiciones hasta recibir respuesta de JPL'} · Rueda para zoom · Arrastra para mover</div>
  </div>
}
