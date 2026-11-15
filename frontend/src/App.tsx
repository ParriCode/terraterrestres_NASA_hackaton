import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'
import { bodyName } from './data/solarSystem'
import { ApiError, requestTransfer } from './api/transfers'
import Icon from './components/Icon'
import PlaybackControls from './components/PlaybackControls'
import SolarSystemView from './components/SolarSystemView'
import TransferForm from './components/TransferForm'
import MissionFailure from './components/MissionFailure'
import TransferSummary from './components/TransferSummary'
import TransferView from './components/TransferView'
import type { TransferRequest, TransferResponse } from './types/transfer'
import { formatDuration, formatUtc, stateAt } from './utils/transfer'

type Journey = { id: string; title: string; response: TransferResponse; visible: boolean; color: string }
type Scene = 'solar' | 'earth'
const COLORS = ['#64ead5', '#f7ba68', '#80aaff', '#f297c1', '#cc9eff', '#7cd6ff']

export default function App() {
  const [origin, setOrigin] = useState("earth")
  const [destination, setDestination] = useState("moon")
  const [pickTarget, setPickTarget] = useState<"origin" | "destination">("destination")
  const [journeys, setJourneys] = useState<Journey[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [scene, setScene] = useState<Scene>('solar')
  const [showForm, setShowForm] = useState(true)
  const [showDrawer, setShowDrawer] = useState(false)
  const [showResults, setShowResults] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [failedMission, setFailedMission] = useState<{ request: TransferRequest; detail: string } | null>(null)
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(21600)
  const controller = useRef<AbortController | null>(null)
  const [previewDate, setPreviewDate] = useState(() => new Date())

  const selected = journeys.find(j => j.id === selectedId) ?? null
  const transfer = selected?.response ?? null
  const duration = transfer?.duration_s ?? 0
  const state = useMemo(() => transfer ? stateAt(transfer.samples, time, transfer.origin_id, transfer.destination_id) : null, [transfer, time])

  useEffect(() => {
    if (!playing || !duration) return
    let last = performance.now(), frame = 0
    const tick = (now: number) => {
      const dt = (now - last) / 1000
      last = now
      setTime(t => {
        const next = t + dt * speed
        if (next >= duration) { setPlaying(false); return duration }
        return next
      })
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, speed, duration])

  async function calculate(request: TransferRequest) {
    controller.current?.abort()
    const signal = new AbortController()
    controller.current = signal
    setBusy(true); setError(''); setFailedMission(null); setPlaying(false)
    try {
      const result = await requestTransfer(request, signal.signal)
      if (signal.signal.aborted) return
      const id = crypto.randomUUID()
      const title = `${result.mission_mode === 'lunar_orbit_return' ? 'Órbita lunar + retorno' : (result.objective === 'energia' ? 'Energía mínima' : 'Distancia mínima')} · ${new Date(result.date).toLocaleDateString('es-ES', { day: '2-digit', month: 'short' })}`
      setJourneys(prev => [...prev, { id, title, response: result, color: COLORS[prev.length % COLORS.length], visible: true }])
      setSelectedId(id); setTime(0); setScene('earth'); setShowForm(false); setShowDrawer(false); setShowResults(true)
    } catch (e) {
      if (signal.signal.aborted) return
      if (e instanceof ApiError && (e.code === 'no_valid_transfer' || e.code === 'no_valid_lunar_orbit_return')) {
        setFailedMission({ request, detail: e.message })
      } else {
        setError(e instanceof Error ? e.message : 'Error desconocido al calcular la transferencia.')
      }
      setShowForm(true)
    } finally {
      if (controller.current === signal) { controller.current = null; setBusy(false) }
    }
  }
  function reviseMission(field?: 'date' | 'duration') {
    setFailedMission(null); setShowForm(true); setShowDrawer(false); setShowResults(false)
    requestAnimationFrame(() => {
      const input = document.getElementById(field === 'date' ? 'mission-date' : 'mission-duration')
      input?.focus()
      input?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    })
  }
  function cancel() { controller.current?.abort(); controller.current = null; setBusy(false) }
  function selectJourney(id: string) {
    setSelectedId(id); setTime(0); setPlaying(false); setScene('earth')
    setShowDrawer(false); setShowForm(false); setShowResults(true)
  }
  function deleteJourney(id: string) {
    setJourneys(prev => prev.filter(j => j.id !== id))
    if (selectedId === id) { setSelectedId(null); setTime(0); setPlaying(false); setShowResults(false) }
  }
  function togglePlayback() {
    if (!transfer) return
    if (!playing && time >= duration) setTime(0)
    setPlaying(p => !p)
  }
  const visibleCount = journeys.filter(j => j.visible).length
  const sceneDate = transfer ? new Date(new Date(transfer.date).getTime() + time * 1000) : previewDate

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-logo"><Icon name="orbit" size={24} /></span>
        <div className="brand-type"><div>ORBITAL<span>4B</span></div><small>EXPLORACIÓN DEL SISTEMA SOLAR</small></div></div>
      <div className="nav-actions">
        <button type="button" className="nav-button" onClick={() => { setShowForm(true); setShowDrawer(false) }}>
          <Icon name="plus" size={14} /> <span>Nueva misión</span></button>
        {selected && <button type="button" className="nav-button subtle-nav" onClick={() => { setShowResults(v => !v); setShowForm(false) }}>
          <Icon name="layers" size={15} /><span>Resultados</span></button>}
        <button type="button" className="nav-button menu-button" aria-expanded={showDrawer} aria-label="Abrir lista de viajes"
          onClick={() => { setShowDrawer(v => !v); setShowForm(false) }}>
          <Icon name="bars" size={19} /><span>Viajes {journeys.length > 0 ? `(${journeys.length})` : ''}</span></button>
      </div>
    </header>
    <main className="stage">
      {scene === 'solar'
        ? <SolarSystemView date={showForm ? previewDate : sceneDate} journeyCount={visibleCount} origin={origin} destination={destination} pickTarget={pickTarget} onSelect={id => {
          if (pickTarget === 'origin') { setOrigin(id); if (id === destination) setDestination(origin); setPickTarget('destination') }
          else if (id !== origin) setDestination(id)
          setShowForm(true)
        }} />
        : <TransferView date={previewDate} transfer={transfer} state={state} time={time} visible={selected?.visible ?? false} color={selected?.color} onSolar={() => setScene('solar')} />}
      <div className="scene-nav">
        <button type="button" className={scene === 'solar' ? 'scene-tab active' : 'scene-tab'} onClick={() => setScene('solar')}>
          <Icon name="globe" size={15} /> Sistema solar</button>
        <button type="button" className={scene === 'earth' ? 'scene-tab active' : 'scene-tab'} onClick={() => setScene('earth')}>
          <Icon name="target" size={15} /> Trayectoria</button>
      </div>
      <div className="mission-panel panel-surface" style={{ display: showForm ? undefined : "none" }} aria-label="Configuración de transferencia">
        <button className="panel-close" type="button" onClick={() => setShowForm(false)} aria-label="Cerrar formulario"><Icon name="x" size={16} /></button>
        <TransferForm origin={origin} destination={destination} onOrigin={setOrigin} onDestination={setDestination} onPick={target => { setPickTarget(target); setScene("solar"); setShowForm(false) }} busy={busy} onSubmit={calculate} onCancel={cancel} onDateChange={setPreviewDate} />
        {error && <div role="alert" className="error-box"><Icon name="alert" size={18} /><span>{error}</span></div>}
      </div>
      {selected && state && showResults && !showForm && <div className="results-overlay panel-surface">
        <button className="panel-close" type="button" aria-label="Cerrar resultados" onClick={() => setShowResults(false)}><Icon name="x" size={16} /></button>
        <TransferSummary transfer={selected.response} state={state} />
      </div>}
      {busy && <div className="loading-overlay" role="status" aria-live="polite">
        <div className="loading-card"><img src="/resource/loading_cohete_nubes.svg" alt="Animación de cohete" />
          <h2>Calculando la misión</h2><p>Consultando NASA/JPL Horizons y resolviendo los candidatos…</p>
          <button type="button" className="ghost-button" onClick={cancel}>Cancelar cálculo</button>
        </div>
      </div>}
      {transfer && <div className="timeline-overlay">
        <div className="timeline-head"><Icon name="clock" size={15} /><span>{selected?.title}</span>
          <span className="timeline-mode">{formatUtc(sceneDate)}</span>
          <button type="button" title="Deseleccionar misión" aria-label="Deseleccionar misión" className="timeline-clear"
            onClick={() => { setSelectedId(null); setPlaying(false); setShowResults(false); setScene('solar') }}><Icon name="x" size={13} /></button></div>
        <PlaybackControls start={new Date(transfer.date)} duration={duration} time={time} playing={playing} speed={speed}
          onToggle={togglePlayback} onReset={() => { setPlaying(false); setTime(0) }}
          onTime={t => { setPlaying(false); setTime(t) }} onSpeed={setSpeed} />
      </div>}
      <div className="source-disclaimer">{scene === 'solar' ? 'Posiciones NASA/JPL proyectadas en 2D. Distancias comprimidas y tamaños ampliados para seleccionar cuerpos.'
        : transfer ? 'Coordenadas y trayectoria de la simulación real del backend.' : 'Vista Tierra–Luna: posiciones JPL Horizons si están disponibles; sin simulación de nave.'}</div>
    </main>
    {failedMission && <MissionFailure request={failedMission.request} detail={failedMission.detail} onRevise={reviseMission} />}
    {showDrawer && <>
      <button className="drawer-backdrop" aria-label="Cerrar menú de viajes" onClick={() => setShowDrawer(false)} />
      <aside className="journey-drawer" aria-label="Mis viajes">
        <div className="drawer-head"><div><small>CENTRO DE MISIONES</small><h2>Mis viajes <span>{journeys.length}</span></h2></div>
          <button type="button" className="icon-button" aria-label="Cerrar menú de viajes" onClick={() => setShowDrawer(false)}><Icon name="x" /></button></div>
        <div className="drawer-scroll">{journeys.length === 0
          ? <div className="drawer-empty"><Icon name="rocket" size={30} /><h3>No hay viajes todavía</h3><p>Configura una transferencia para ver su trayectoria.</p></div>
          : journeys.map(j => <div key={j.id} className={j.id === selectedId ? 'journey-card selected' : 'journey-card'}>
            <button type="button" className="journey-select" onClick={() => selectJourney(j.id)}>
              <span className="journey-dot" style={{ background: j.color }} /><strong>{j.title}</strong><span className="journey-tag">JPL</span>
              <small>{bodyName(j.response.origin_id ?? "earth")} <Icon name="arrow" size={11} /> {bodyName(j.response.destination_id ?? "moon")}{j.response.mission_mode === 'lunar_orbit_return' ? ' (órbita) → Tierra' : ''} · {formatDuration(j.response.duration_s)}</small>
            </button>
            <div className="journey-actions"><button type="button" title={j.visible ? 'Ocultar ruta' : 'Mostrar ruta'}
              aria-label={j.visible ? `Ocultar ${j.title}` : `Mostrar ${j.title}`}
              onClick={() => setJourneys(prev => prev.map(v => v.id === j.id ? { ...v, visible: !v.visible } : v))}>
              <Icon name={j.visible ? 'eye' : 'eye-off'} size={16} />{j.visible ? 'Visible' : 'Oculta'}</button>
              <button type="button" aria-label={`Eliminar ${j.title}`} title="Eliminar viaje" onClick={() => deleteJourney(j.id)}><Icon name="trash" size={15} /></button></div>
          </div>)}</div>
        <div className="drawer-footer"><button type="button" className="primary-button" onClick={() => { setShowDrawer(false); setShowForm(true) }}>
          <Icon name="plus" size={15} />Crear viaje</button></div>
      </aside>
    </>}
  </div>
}
