import { useEffect, useMemo, useRef, useState } from 'react'
import type { TransferResponse, TransferState, Vec3 } from '../types/transfer'
import { PLANETS, planetPosition, bodyName } from '../data/solarSystem'
import { frameToIcrf, icrfToEcliptic } from '../utils/heliocentric'
import { SolarSpaceRenderer } from '../renderer/SpaceRenderer'
import Icon from './Icon'

type Props = {
  date: Date
  transfer: TransferResponse | null
  state: TransferState | null
  visible?: boolean
  color?: string
  onEarth: () => void
}

/** Sistema solar 3D: mismos elementos medios JPL que el SVG de esta rama.
 * Si hay una misión a Marte, se priorizan Tierra/Marte/nave de Horizons (backend).
 * Nunca se mueven las coordenadas físicas por alterar las dimensiones visuales. */
export default function SolarSystemView3D({ date, transfer, state, visible = true, color = '#70efd8', onEarth }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const labels = useRef<Record<string, HTMLButtonElement | null>>({})
  const shipLabel = useRef<HTMLDivElement>(null)
  const renderer = useRef<SolarSpaceRenderer | null>(null)
  const [error, setError] = useState('')
  const hasMarsMission = transfer?.destination === 'mars' && Boolean(state?.sun_m && state?.mars_m)
  const positions = useMemo(() => {
    const result: Record<string, Vec3> = Object.fromEntries(PLANETS.map(p => [p.id, planetPosition(p, date)]))
    if (hasMarsMission && transfer && state?.sun_m && state.mars_m) {
      const relative = (v: readonly number[]) => icrfToEcliptic(frameToIcrf(
        [v[0] - state.sun_m![0], v[1] - state.sun_m![1], v[2] - state.sun_m![2]], transfer.basis_icrf))
      result.earth = relative(state.earth_m)
      result.mars = relative(state.mars_m)
      result.moon = relative(state.moon_m)
    }
    return result
  }, [date, hasMarsMission, transfer, state])
  useEffect(() => {
    if (!canvas.current) return
    try {
      const instance = new SolarSpaceRenderer(canvas.current, labels.current, shipLabel.current)
      renderer.current = instance
      instance.setBodies(positions, date)
      instance.setMission(transfer, color, visible)
      instance.setFrame(state)
      return () => { instance.dispose(); if (renderer.current === instance) renderer.current = null }
    } catch (reason) { queueMicrotask(() => setError(reason instanceof Error ? reason.message : 'No se pudo iniciar WebGL')) }
    // Solo crear el contexto WebGL al montar el visor, no en cada fotograma.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => { renderer.current?.setBodies(positions, date) }, [positions, date])
  useEffect(() => { renderer.current?.setMission(transfer, color, visible) }, [transfer, color, visible])
  useEffect(() => { renderer.current?.setFrame(state) }, [state])

  return <div className="solar-view solar-view-3d">
    <canvas ref={canvas} className="space-canvas"
      aria-label="Sistema solar tridimensional con posiciones medias JPL, y posiciones de Horizons para misiones a Marte. Arrastra para girar y rueda para acercar." />
    {PLANETS.map(planet => <button key={planet.id} ref={element => { labels.current[planet.id] = element }}
      type="button" className="solar-3d-label" style={{ display: 'none' }}
      onClick={() => planet.id === 'earth' ? onEarth() : renderer.current?.focus(planet.id)}
      title={planet.id === 'earth' ? 'Ver Tierra–Luna' : `Enfocar ${planet.name}`}>{planet.name}</button>)}
    <button type="button" ref={element => { labels.current.sun = element }} className="solar-3d-label"
      onClick={() => renderer.current?.focus('sun')} style={{ display: 'none' }}>Sol</button>
    <div ref={shipLabel} className="space-label space-label-ship" style={{ display: 'none' }}>NAVE · MARTE</div>
    <div className="scene-heading">
      <span className="eyebrow">SISTEMA SOLAR · VISOR 3D</span>
      <h1>{hasMarsMission ? 'Tierra → Marte · crucero' : 'Nuestro sistema solar'}</h1>
      <p>{hasMarsMission ? 'Trayectoria del backend con Tierra y Marte en JPL Horizons. Otros planetas: elementos orbitales medios JPL.'
        : `Posiciones heliocéntricas aproximadas JPL · ${date.toLocaleDateString('es-ES', { timeZone: 'UTC' })}.`}</p>
    </div>
    <div className="map-tools space-controls" aria-label="Cámara del sistema solar 3D">
      <button type="button" className="icon-button" onClick={() => renderer.current?.zoom(.72)} aria-label="Acercar" title="Acercar"><Icon name="plus" /></button>
      <button type="button" className="icon-button" onClick={() => renderer.current?.zoom(1.4)} aria-label="Alejar" title="Alejar"><Icon name="minus" /></button>
      <button type="button" className="icon-button" onClick={() => renderer.current?.home()} aria-label="Mostrar sistema completo" title="Sistema completo"><Icon name="crosshair" /></button>
      <button type="button" className="icon-button" onClick={() => renderer.current?.focus('earth')} aria-label="Enfocar Tierra" title="Tierra"><span aria-hidden="true">🌍</span></button>
      <button type="button" className="icon-button" onClick={() => renderer.current?.focus('mars')} aria-label="Enfocar Marte" title="Marte"><span aria-hidden="true">🔴</span></button>
    </div>
    {error && <div className="space-render-error" role="alert"><strong>Visor 3D no disponible</strong><p>{error}</p><button type="button" onClick={() => renderer.current?.home()}>Restablecer vista</button></div>}
    <div className="view-legend space-legend solar-3d-legend">Arrastra para orbitar · Rueda para zoom · Clic sobre el planeta para enfocar · Las distancias y los radios visibles tienen escalas distintas · {bodyName('mars')} y la nave siguen la misión cuando hay datos JPL.</div>
  </div>
}
