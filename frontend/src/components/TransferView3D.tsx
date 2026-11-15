import { useEffect, useRef, useState } from 'react'
import type { TransferResponse, TransferState } from '../types/transfer'
import type { EarthMoonEphemeris, SunDirectionEphemeris } from '../api/ephemerides'
import { SpaceRenderer } from '../renderer/SpaceRenderer'
import Icon from './Icon'

type Props = {
  preview: EarthMoonEphemeris | null
  previewError: string
  sun: SunDirectionEphemeris | null
  sunError: string
  date: Date
  transfer: TransferResponse | null
  state: TransferState | null
  time: number
  visible?: boolean
  color?: string
}

/**
 * Reemplazo 3D del SVG. Los cuerpos y el cohete se sitúan con las coordenadas
 * NASA/JPL o con las muestras de la misión recibidas, nunca con órbitas inventadas.
 */
export default function TransferView3D({ date, transfer, state, preview, previewError, sun, sunError, visible = true, color = '#64ead5' }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const earthLabel = useRef<HTMLDivElement>(null)
  const moonLabel = useRef<HTMLDivElement>(null)
  const shipLabel = useRef<HTMLDivElement>(null)
  const renderer = useRef<SpaceRenderer | null>(null)
  const sunArrow = useRef<HTMLSpanElement>(null)
  const [rendererError, setRendererError] = useState('')
  const [enhanced, setEnhanced] = useState(true)
  const [showTracks, setShowTracks] = useState(true)
  useEffect(() => {
    if (!canvas.current) return
    try {
      const view = new SpaceRenderer(canvas.current, {
        earth: earthLabel.current, moon: moonLabel.current, ship: shipLabel.current,
      }, sunArrow.current)
      renderer.current = view
      // Las props pueden haberse recibido antes de montar WebGL: aplicar instantáneamente.
      view.setMission(transfer, color, visible)
      view.setPreview(transfer ? null : preview)
      view.setFrame(state, date, sun)
      view.setEnhanced(enhanced)
      view.setTracks(showTracks)
      setRendererError('')
      return () => { view.dispose(); if (renderer.current === view) renderer.current = null }
    } catch (error) {
      setRendererError(error instanceof Error ? error.message : 'No se pudo iniciar el visor WebGL.')
    }
  // El renderizador se monta una sola vez mientras se está en modo 3D.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => { renderer.current?.setMission(transfer, color, visible) }, [transfer, color, visible])
  useEffect(() => { renderer.current?.setPreview(transfer ? null : preview) }, [transfer, preview])
  useEffect(() => { renderer.current?.setFrame(state, date, sun) }, [state, date, sun])
  useEffect(() => { renderer.current?.setEnhanced(enhanced) }, [enhanced])
  useEffect(() => { renderer.current?.setTracks(showTracks) }, [showTracks])

  const heading = transfer?.mission_mode === 'lunar_orbit_return'
    ? 'Órbita lunar y regreso'
    : transfer?.mission_mode === 'free_return'
      ? 'Retorno libre Tierra–Luna–Tierra'
      : transfer ? 'Transferencia lunar calculada'
        : preview ? 'Tierra y Luna en la fecha seleccionada'
          : previewError ? 'Efemérides no disponibles' : 'Consultando NASA/JPL Horizons…'

  return <div className="transfer-view transfer-view-3d">
    <canvas className="space-canvas" ref={canvas} aria-label="Visor tridimensional interactivo del sistema Tierra–Luna. Arrastra para orbitar, rueda para zoom y botón derecho para desplazar." />
    <div ref={earthLabel} className="space-label space-label-earth" style={{ display: 'none' }}>TIERRA</div>
    <div ref={moonLabel} className="space-label space-label-moon" style={{ display: 'none' }}>LUNA</div>
    <div ref={shipLabel} className="space-label space-label-ship" style={{ display: 'none' }}>NAVE · ORBITAL4B</div>

    <div className="scene-heading scene-heading-local space-heading">
      <span className="eyebrow">SISTEMA TIERRA–LUNA <span className="space-dimension">VISOR 3D</span></span>
      <h1>{heading}</h1>
      <p>{transfer
        ? `${transfer.source}: trayectoria y posiciones del motor orbital, reconstruidas en 3D.`
        : previewError || (preview
          ? `Coordenadas ICRF de NASA/JPL · ${new Date(preview.date).toLocaleString('es-ES', { timeZone: 'UTC' })} UTC`
          : 'Cargando posiciones reales para la fecha UTC elegida; no se utilizan efemérides ficticias.')}</p>
    </div>

    <div className="sun-indicator space-sun" title={sun
      ? `Dirección Tierra → Sol de NASA/JPL Horizons (${sun.date}). El Sol está representado como luz lejana, fuera de escala.`
      : sunError || 'Consultando dirección solar en NASA/JPL Horizons'}>
      <img src="/resource/sol.svg" alt="" draggable={false} /><span>Sol</span>
      <span ref={sunArrow} className="sun-indicator__arrow" style={{ display: sun ? 'inline-flex' : 'none' }}
        aria-label="Dirección del Sol en la cámara 3D"><Icon name="arrow" size={17} /></span>
      {sun ? <span className="space-sun-source">JPL · dirección 3D</span>
        : <span className="sun-indicator__unavailable">{sunError ? 'Sin datos' : '…'}</span>}
    </div>

    <div className="map-tools space-controls" aria-label="Controles de la cámara 3D">
      <button type="button" className="icon-button" onClick={() => renderer.current?.zoom(.72)} aria-label="Acercar cámara" title="Acercar"><Icon name="plus" /></button>
      <button type="button" className="icon-button" onClick={() => renderer.current?.zoom(1.4)} aria-label="Alejar cámara" title="Alejar"><Icon name="minus" /></button>
      <button type="button" className="icon-button" onClick={() => renderer.current?.focusOn('system')} aria-label="Mostrar sistema completo" title="Ver sistema completo"><Icon name="crosshair" /></button>
      <div className="space-control-divider" />
      <button type="button" className="icon-button space-target" onClick={() => renderer.current?.focusOn('earth')} aria-label="Enfocar Tierra" title="Enfocar Tierra"><span aria-hidden="true">🌍</span></button>
      <button type="button" className="icon-button space-target" onClick={() => renderer.current?.focusOn('moon')} aria-label="Enfocar Luna" title="Enfocar Luna"><span aria-hidden="true">🌕</span></button>
      {transfer && visible && <button type="button" className="icon-button" onClick={() => renderer.current?.focusOn('ship')} aria-label="Seguir nave" title="Seguir nave"><Icon name="rocket" /></button>}
    </div>

    <div className="space-view-options" aria-label="Opciones visuales">
      <label title="Cambia únicamente los radios dibujados. Las distancias y trayectorias mantienen las coordenadas reales.">
        <input type="checkbox" checked={enhanced} onChange={e => setEnhanced(e.target.checked)} />
        <span>Tamaños ampliados</span>
      </label>
      {transfer && <label title="Muestra las posiciones de los cuerpos durante el intervalo calculado.">
        <input type="checkbox" checked={showTracks} onChange={e => setShowTracks(e.target.checked)} />
        <span>Rastros orbitales</span>
      </label>}
    </div>

    {transfer && transfer.samples.some(sample => {
      const p = sample.position_m, m = sample.body_positions_m.moon
      const distance = Math.hypot(p[0] - m[0], p[1] - m[1], p[2] - m[2])
      return distance < transfer.bodies.moon.radius_m
    }) && <div className="space-physics-warning" role="status">
      El backend devuelve al menos una posición dentro de la Luna. La vista no modifica la trayectoria física.
    </div>}
    {rendererError && <div className="space-render-error" role="alert"><strong>No se puede mostrar el 3D</strong><p>{rendererError}</p></div>}
    <div className="view-legend space-legend">Arrastra para girar en 3D · Rueda para zoom · Botón derecho para desplazar · {enhanced ? 'Escala visual adaptada para evitar solapamientos'  : 'Radios físicos; nave reducida al acercarse a los cuerpos'} · {sun ? 'Iluminación: dirección JPL' : 'Sin dirección solar JPL: iluminación provisional'}</div>
  </div>
}
