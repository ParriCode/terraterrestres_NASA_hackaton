import { useEffect, useMemo, useRef, useState } from 'react'
import type { PointerEvent, WheelEvent } from 'react'
import { PLANETS, planetaryPosition, moonAngle, SOLAR_CENTER, ORBIT_FLAT } from '../data/solarSystem'
import type { EphemerisSnapshot, Journey, TrajectorySample } from '../types/simulation'
import { clamp, elapsedAt, projectRelativeToEarth, sampleAt } from '../utils/trajectory'
import Icon from './Icon'

type Props = {
  date: Date; journeys: Journey[]; selectedJourneyId: string | null;
  onSelectJourney: (id: string) => void; ephemeris: EphemerisSnapshot | null; focusEarthSignal: number;
}
type Camera = { x: number; y: number; zoom: number }
const MID = SOLAR_CENTER
const BASE: Camera = { x: MID.x, y: MID.y, zoom: 1 }
const LOCAL_PX_PER_M = 315 / 384_400_000

// Estrellas constantes, sin cambios aleatorios en cada render
const stars = Array.from({ length: 245 }, (_, i) => {
  const x = (i * 763.71 + 113) % 1400, y = (i * 443.29 + 57) % 790
  return { x, y, r: i % 13 === 0 ? 1.2 : i % 5 === 0 ? 0.8 : 0.45, opacity: 0.2 + (i % 7) * 0.08 }
})

function pathFor(samples: TrajectorySample[], maxTime: number) {
  if (!samples.length) return { past: '', future: '' }
  const stride = Math.max(1, Math.floor(samples.length / 450))
  const points = samples.filter((_, i) => i % stride === 0 || i === samples.length - 1)
    .map(s => ({ t: s.t_s, ...projectRelativeToEarth(s, LOCAL_PX_PER_M) }))
  const draw = (arr: typeof points) => arr.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join(' ')
  const past = points.filter(p => p.t <= maxTime)
  const future = points.filter(p => p.t > maxTime)
  if (past.length && future.length) future.unshift(past[past.length - 1])
  if (!past.length && future.length) past.push(future[0])
  return { past: draw(past), future: draw(future) }
}

/** Vista esquemática de rutas Tierra–Luna en la panorámica (NO escala física) */
function schematicSolarRoute(origin: { x: number; y: number }, index: number, progress: number, freeReturn = false) {
  const angle = -1.3 + index * 1.16
  const length = 72 + (index % 3) * 19
  const end = { x: origin.x + Math.cos(angle) * length, y: origin.y + Math.sin(angle) * length * .85 }
  const mid = { x: (origin.x + end.x) / 2, y: (origin.y + end.y) / 2 }
  const normal = { x: -Math.sin(angle) * 29, y: Math.cos(angle) * 29 }
  const c1 = { x: mid.x + normal.x - 18, y: mid.y + normal.y - 13 }
  const c2 = { x: mid.x + normal.x + 19, y: mid.y + normal.y + 15 }
  const at = (t: number) => {
    const s = 1 - t
    return {
      x: s * s * s * origin.x + 3 * s * s * t * c1.x + 3 * s * t * t * c2.x + t * t * t * end.x,
      y: s * s * s * origin.y + 3 * s * s * t * c1.y + 3 * s * t * t * c2.y + t * t * t * end.y
    }
  }
  const back1 = { x: end.x + normal.x * .8 + 19, y: end.y + normal.y * .8 - 6 }
  const back2 = { x: origin.x - normal.x * .8 - 22, y: origin.y - normal.y * .8 + 4 }
  const returnAt = (t: number) => {
    const s = 1 - t
    return {
      x: s * s * s * end.x + 3 * s * s * t * back1.x + 3 * s * t * t * back2.x + t * t * t * origin.x,
      y: s * s * s * end.y + 3 * s * s * t * back1.y + 3 * s * t * t * back2.y + t * t * t * origin.y
    }
  }
  const pointAt = (t: number) => freeReturn ? t <= .5 ? at(t * 2) : returnAt((t - .5) * 2) : at(t)
  const points = Array.from({ length: 61 }, (_, i) => ({ t: i / 60, ...pointAt(i / 60) }))
  const draw = (arr: typeof points) => arr.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')
  const past = points.filter(p => p.t <= progress)
  const future = points.filter(p => p.t > progress)
  if (!past.length) past.push(points[0])
  if (future.length) future.unshift(past[past.length - 1])
  return { past: draw(past), future: draw(future), tip: pointAt(clamp(progress, 0, 1)) }
}

export default function OrbitView({ date, journeys, selectedJourneyId, onSelectJourney, ephemeris, focusEarthSignal }: Props) {
  const [scope, setScope] = useState<'solar' | 'earth'>('solar')
  const [camera, setCamera] = useState<Camera>(BASE)
  const [focused, setFocused] = useState<string | null>(null)
  const [hoverPlanet, setHoverPlanet] = useState<string | null>(null)
  const svg = useRef<SVGSVGElement>(null)
  const drag = useRef<{ x: number; y: number; camera: Camera; moved: boolean } | null>(null)
  const suppressClick = useRef(false)
  useEffect(() => { if (focusEarthSignal > 0) { setScope('earth'); setCamera(BASE); setFocused('earth') } }, [focusEarthSignal])
  const visibleJourneys = journeys.filter(j => j.visible)
  const selectedJourney = journeys.find(j => j.id === selectedJourneyId) ?? null

  const planets = useMemo(() => PLANETS.map(p => ({ ...p, point: planetaryPosition(p, date, ephemeris) })), [date, ephemeris])
  const earth = planets.find(p => p.id === 'earth')!
  const localSample = selectedJourney ? sampleAt(selectedJourney.result.samples, elapsedAt(selectedJourney, date)) : null
  const bodyEarth = localSample?.body_positions_m.earth
  const bodyMoon = localSample?.body_positions_m.moon
  const ang = moonAngle(date, ephemeris)
  const moonPoint = bodyEarth && bodyMoon
    ? { x: MID.x + (bodyMoon[0] - bodyEarth[0]) * LOCAL_PX_PER_M, y: MID.y - (bodyMoon[1] - bodyEarth[1]) * LOCAL_PX_PER_M }
    : { x: MID.x + Math.cos(ang) * 315, y: MID.y - Math.sin(ang) * 315 }

  function positionFromPointer(event: { clientX: number; clientY: number }): { x: number; y: number } {
    if (!svg.current) return MID
    const matrix = svg.current.getScreenCTM()
    if (!matrix) return MID
    const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
    return { x: p.x, y: p.y }
  }
  function zoomBy(factor: number, anchor = MID) {
    setCamera(old => {
      const zoom = clamp(old.zoom * factor, 1, scope === 'earth' ? 60 : 13)
      const worldX = old.x + (anchor.x - MID.x) / old.zoom
      const worldY = old.y + (anchor.y - MID.y) / old.zoom
      return { zoom, x: worldX - (anchor.x - MID.x) / zoom, y: worldY - (anchor.y - MID.y) / zoom }
    })
  }
  function wheel(e: WheelEvent<SVGSVGElement>) {
    e.preventDefault()
    const mouse = positionFromPointer(e)
    // Al acercarse suficientemente a la Tierra, pasar a detalle Tierra–Luna
    // Es un cambio de escala de DISEÑO, no una conversión métrica del mapa general
    const earthScreen = { x: MID.x + (earth.point.x - camera.x) * camera.zoom, y: MID.y + (earth.point.y - camera.y) * camera.zoom }
    if (scope === 'solar' && e.deltaY < 0 && camera.zoom > 4.2 && Math.hypot(mouse.x - earthScreen.x, mouse.y - earthScreen.y) < 75) {
      showEarth(); return
    }
    if (scope === 'earth' && e.deltaY > 0 && camera.zoom <= 1.01) { showSolar(); return }
    zoomBy(e.deltaY < 0 ? 1.17 : 1 / 1.17, mouse)
  }
  function pointerDown(e: PointerEvent<SVGSVGElement>) {
    if (e.button !== 0) return
    e.preventDefault() // Inicia movimiento, no selección de texto nativa
    const p = positionFromPointer(e)
    drag.current = { x: p.x, y: p.y, camera, moved: false }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  function pointerMove(e: PointerEvent<SVGSVGElement>) {
    if (!drag.current) return
    const p = positionFromPointer(e)
    const dx = p.x - drag.current.x, dy = p.y - drag.current.y
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.current.moved = true
    setCamera({
      ...drag.current.camera, x: drag.current.camera.x - dx / drag.current.camera.zoom,
      y: drag.current.camera.y - dy / drag.current.camera.zoom
    })
  }
  function pointerUp() {
    suppressClick.current = Boolean(drag.current?.moved)
    drag.current = null
    if (suppressClick.current) window.setTimeout(() => { suppressClick.current = false }, 100)
  }
  function showEarth() { setScope('earth'); setCamera(BASE); setFocused('earth') }
  function showSolar() { setScope('solar'); setCamera(BASE); setFocused(null) }
  function planetClick(id: string) {
    if (suppressClick.current) { suppressClick.current = false; return }
    if (id === 'earth') { showEarth(); return }
    const p = planets.find(p => p.id === id)
    if (p) { setFocused(id); setCamera({ x: p.point.x, y: p.point.y, zoom: 3.3 }) }
  }

  return <div className="orbital-stage">
    <svg ref={svg} className="orbital-svg" viewBox="0 0 1400 790" preserveAspectRatio="xMidYMid meet"
      onWheel={wheel} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={pointerUp} onLostPointerCapture={pointerUp} onDragStart={e => e.preventDefault()}
      role="img" aria-label={scope === 'solar' ? 'Vista interactiva del sistema solar' : 'Vista Tierra y Luna con trayectorias'}>
      <defs>
        <radialGradient id="space-grad"><stop offset="0" stopColor="#11213c" /><stop offset="0.6" stopColor="#091428" /><stop offset="1" stopColor="#050b18" /></radialGradient>
        <radialGradient id="sun-glow"><stop stopColor="#ffb968" stopOpacity=".44" /><stop offset=".35" stopColor="#fca844" stopOpacity=".16" /><stop offset="1" stopColor="#fca844" stopOpacity="0" /></radialGradient>
        <radialGradient id="earth-fallback" cx="36%" cy="26%"><stop stopColor="#4acaf9" /><stop offset="1" stopColor="#1558a5" /></radialGradient>
        <filter id="planet-halo"><feGaussianBlur stdDeviation="8" /></filter>
      </defs>
      <rect x="0" y="0" width="1400" height="790" fill="url(#space-grad)" />
      {stars.map((s, i) => <circle key={i} cx={s.x} cy={s.y} r={s.r} opacity={s.opacity} fill="#bddeff" />)}
      <g transform={`translate(${MID.x} ${MID.y}) scale(${camera.zoom}) translate(${-camera.x} ${-camera.y})`}>
        {scope === 'solar' ? <>
          {PLANETS.map(p => <ellipse key={`orbit-${p.id}`} cx={MID.x} cy={MID.y}
            rx={p.radius} ry={p.radius * ORBIT_FLAT} className="solar-orbit" />)}
          <circle cx={MID.x} cy={MID.y} r="116" fill="url(#sun-glow)" />
          <circle cx={MID.x} cy={MID.y} r="25" fill="#faaa3b" opacity=".12" filter="url(#planet-halo)" />
          <image href="/resource/sol.svg" x={MID.x - 29} y={MID.y - 29} width="58" height="58" />
          <circle cx={MID.x} cy={MID.y} r="20" fill="#f6a43d" opacity=".12" pointerEvents="none" />
          <text x={MID.x} y={MID.y + 49} className="planet-label">Sol</text>
          {visibleJourneys.map((j, idx) => {
            const route = schematicSolarRoute(earth.point, idx, elapsedAt(j, date) / Math.max(1, j.result.diagnostics.final_time_s), j.route_kind === 'lunar_free_return')
            return <g key={`overview-${j.id}`} className="schematic-route">
              <path d={route.future} fill="none" stroke={j.color} strokeWidth="1.8" strokeDasharray="5 6" strokeOpacity=".65" />
              <path d={route.past} fill="none" stroke={j.color} strokeWidth="2.5" strokeOpacity=".95" />
              <circle cx={route.tip.x} cy={route.tip.y} r="4" fill={j.color} stroke="#071627" strokeWidth="1.2" />
              <text x={route.tip.x + 8} y={route.tip.y - 7} fontSize="10" fontWeight="700" fill={j.color}
                onClick={() => { if (!suppressClick.current) { onSelectJourney(j.id); showEarth() } }} style={{ cursor: 'pointer' }}>{j.name}</text>
            </g>
          })}
          {planets.map(p => <g key={p.id} className="planet-point" onPointerEnter={() => setHoverPlanet(p.id)} onPointerLeave={() => setHoverPlanet(null)}
            onClick={() => planetClick(p.id)} role="button" tabIndex={0} aria-label={`Enfocar ${p.name}`}
            onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); planetClick(p.id) } }}>
            {p.id === focused || p.id === hoverPlanet ? <circle cx={p.point.x} cy={p.point.y} r={p.size / 2 + 13} fill="none" stroke={p.color} strokeWidth="1.1" opacity=".65" /> : null}
            <circle cx={p.point.x} cy={p.point.y} r={Math.max(5, p.size / 2 - 2)} fill={p.color} opacity=".8" />
            <image href={`/resource/${p.asset}`} x={p.point.x - p.size / 2} y={p.point.y - p.size / 2} width={p.size} height={p.size} />
            <text x={p.point.x} y={p.point.y + p.size / 2 + 17} className="planet-label">{p.name}</text>
            {p.id === 'earth' && visibleJourneys.length > 0 ? <g>
              <circle cx={p.point.x + p.size / 2 + 11} cy={p.point.y - p.size / 2 - 9} r="12" fill="#243cf0" stroke="#7fbcff" strokeWidth="1" />
              <text x={p.point.x + p.size / 2 + 11} y={p.point.y - p.size / 2 - 5} textAnchor="middle" fill="#fff" fontSize="11" fontWeight="700">{visibleJourneys.length}</text>
            </g> : null}
          </g>)}
        </> : <>
          <circle cx={MID.x} cy={MID.y} r={315} fill="none" stroke="#4c6385" strokeOpacity=".46" strokeDasharray="5 9" strokeWidth="1.5" />
          <circle cx={MID.x} cy={MID.y} r={32} fill="#4bb7ff" opacity=".14" filter="url(#planet-halo)" />
          <circle cx={MID.x} cy={MID.y} r={22} fill="url(#earth-fallback)" />
          <image href="/resource/tierra.svg" x={MID.x - 29} y={MID.y - 29} width="58" height="58" />
          <text x={MID.x} y={MID.y + 52} className="local-label">Tierra</text>
          <circle cx={moonPoint.x} cy={moonPoint.y} r="13" fill="#b5bac7" />
          <image href="/resource/luna.svg" x={moonPoint.x - 17} y={moonPoint.y - 17} width="34" height="34" />
          <text x={moonPoint.x} y={moonPoint.y + 32} className="local-label">Luna</text>
          {visibleJourneys.map(j => {
            const elapsed = elapsedAt(j, date)
            const paths = pathFor(j.result.samples, elapsed)
            const sample = sampleAt(j.result.samples, elapsed)
            const pt = sample ? projectRelativeToEarth(sample, LOCAL_PX_PER_M) : null
            const isSelected = j.id === selectedJourneyId
            const radius = 4.4 / camera.zoom
            return <g key={j.id} className="journey-path">
              <path d={paths.future} fill="none" stroke={j.color} strokeWidth={(isSelected ? 2.7 : 1.7) / camera.zoom} strokeDasharray={`${8 / camera.zoom} ${10 / camera.zoom}`} strokeLinecap="round" opacity={isSelected ? .9 : .54} vectorEffect="non-scaling-stroke" />
              <path d={paths.past} fill="none" stroke={j.color} strokeWidth={(isSelected ? 3.4 : 2.2) / camera.zoom} strokeLinecap="round" opacity={isSelected ? 1 : .7} vectorEffect="non-scaling-stroke" />
              {pt && <g className="ship-point" onClick={() => onSelectJourney(j.id)} role="button" tabIndex={0} aria-label={`Ver ${j.name}`}
                onKeyDown={e => { if (e.key === 'Enter') { onSelectJourney(j.id) } }}>
                <circle cx={pt.x} cy={pt.y} r={radius * 3.6} fill={j.color} opacity=".12" />
                {camera.zoom < 2.5 ? <><circle cx={pt.x} cy={pt.y} r={radius + 2 / camera.zoom} fill={j.color} stroke="#fff" strokeWidth={1 / camera.zoom} /></>
                  : <image href="/resource/nave_espacial.svg" x={pt.x - 19 / camera.zoom} y={pt.y - 19 / camera.zoom} width={38 / camera.zoom} height={38 / camera.zoom} />}
                {isSelected && <text x={pt.x} y={pt.y - 17 / camera.zoom} fontSize={12 / camera.zoom} textAnchor="middle" fill={j.color} fontWeight="700">{j.name}</text>}
              </g>}
            </g>
          })}
        </>}
      </g>
    </svg>
    <div className="stage-top-left">
      <span className="eyebrow"><span className="pulse-dot" />{scope === 'solar' ? 'EXPLORADOR DEL SISTEMA SOLAR' : 'DETALLE DEL SISTEMA TIERRA–LUNA'}</span>
      <h1>{scope === 'solar' ? 'Un universo por explorar.' : 'Cada misión cuenta.'}</h1>
      <p>{scope === 'solar' ? 'Selecciona un planeta o acerca la vista.' : 'Sigue tus trayectorias, inspecciona la nave y cambia el tiempo.'}</p>
    </div>
    <div className="stage-status">
      <Icon name="info" size={15} />
      {ephemeris ? 'Geometría con datos externos · escala visual comprimida' : 'Vista orbital ilustrativa · no son efemérides reales'}
    </div>
    <div className="map-toolbar" aria-label="Herramientas del mapa">
      {scope === 'earth' ? <button className="icon-button" onClick={showSolar} title="Volver al sistema solar" aria-label="Volver al sistema solar"><Icon name="chevron-left" /></button> : null}
      <button className="icon-button" onClick={() => zoomBy(1.5)} title="Acercar" aria-label="Acercar"><Icon name="plus" /></button>
      <button className="icon-button" onClick={() => zoomBy(1 / 1.5)} title="Alejar" aria-label="Alejar"><Icon name="minus" /></button>
      <button className="icon-button" onClick={() => setCamera(BASE)} title="Centrar" aria-label="Centrar vista"><Icon name="crosshair" /></button>
      {scope === 'solar' ? <button className="icon-button earth-button" onClick={showEarth} title="Explorar Tierra y Luna" aria-label="Explorar Tierra y Luna"><Icon name="globe" /></button> : null}
    </div>
    <div className="stage-bottom-label">
      <span className="small-dot" />{scope === 'solar' ? (visibleJourneys.length ? 'Rutas panorámicas esquemáticas · Sol · 8 planetas' : 'Sol · 8 planetas') : 'Tierra · Luna'}
      <span className="divider-small" />Zoom {camera.zoom.toFixed(1)}×
      <span className="divider-small" />Rueda para zoom · arrastra para mover
    </div>
  </div>
}
