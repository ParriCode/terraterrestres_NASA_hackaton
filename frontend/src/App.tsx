import { useEffect, useMemo, useState } from 'react'
import './App.css'
import { fetchEphemerides, runSimulation } from './api/simulations'
import Icon from './components/Icon'
import JourneyDrawer from './components/JourneyDrawer'
import OrbitView from './components/OrbitView'
import PlaybackControls from './components/PlaybackControls'
import type { TimeMode } from './components/PlaybackControls'
import ResultsPanel from './components/ResultsPanel'
import SimulationForm from './components/SimulationForm'
import type { NewJourneyForm } from './components/SimulationForm'
import { createDemoSimulation } from './mocks/demo'
import type { EphemerisSnapshot, Journey } from './types/simulation'

const STORAGE_KEY = 'orbital4b.p4.journeys.v1'
const COLORS = ['#48dfce', '#ffbd69', '#aa9cff', '#ff7890', '#71b6ff', '#d4ee70', '#f0a7f2', '#6cdbc0']

function getSavedJourneys(): Journey[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((x): x is Journey => x && typeof x.id === 'string'
      && typeof x.name === 'string' && typeof x.launch_iso === 'string'
      && (x.source === 'demo' || x.source === 'backend')
      && Array.isArray(x.result?.samples) && typeof x.result?.diagnostics?.final_time_s === 'number')
  } catch { return [] }
}
function saveJourneys(journeys: Journey[]) {
  try {
    // Límite de tamaño para evitar sobrecargar localStorage con muestras de Python
    const data = journeys.map(j => {
      const samples = j.result.samples
      const stride = Math.max(1, Math.ceil(samples.length / 650))
      return { ...j, result: { ...j.result, samples: samples.filter((_, i) => i % stride === 0 || i === samples.length - 1) } }
    })
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data))
  } catch { /* Cuota llena: el viaje continúa funcionando durante esta sesión */ }
}

export default function App() {
  const [journeys, setJourneys] = useState<Journey[]>(getSavedJourneys)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [formOpen, setFormOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [clock, setClock] = useState<Date>(() => new Date())
  const [timeMode, setTimeMode] = useState<TimeMode>('live')
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(21600)
  const [ephemeris, setEphemeris] = useState<EphemerisSnapshot | null>(null)
  const [focusEarthSignal, setFocusEarthSignal] = useState(0)
  const selected = useMemo(() => journeys.find(j => j.id === selectedId) ?? null, [journeys, selectedId])
  const minuteBucket = Math.floor(clock.getTime() / 60_000)

  useEffect(() => saveJourneys(journeys), [journeys])
  useEffect(() => {
    if (timeMode !== 'live') return
    setClock(new Date())
    const interval = window.setInterval(() => setClock(new Date()), 1000)
    return () => window.clearInterval(interval)
  }, [timeMode])
  useEffect(() => {
    if (timeMode !== 'manual' || !playing || !selected) return
    let last = performance.now()
    const timer = window.setInterval(() => {
      const now = performance.now(), delta = (now - last) / 1000
      last = now
      setClock(old => {
        const end = new Date(selected.launch_iso).getTime() + selected.result.diagnostics.final_time_s * 1000
        const next = old.getTime() + delta * speed * 1000
        if (next >= end) { setPlaying(false); return new Date(end) }
        return new Date(next)
      })
    }, 70)
    return () => window.clearInterval(timer)
  }, [timeMode, playing, speed, selected])
  useEffect(() => {
    const controller = new AbortController()
    const handle = window.setTimeout(() => {
      fetchEphemerides(new Date(minuteBucket * 60_000).toISOString(), controller.signal)
        .then(setEphemeris)
        .catch(() => setEphemeris(null))
    }, 450)
    return () => { controller.abort(); window.clearTimeout(handle) }
  }, [minuteBucket])

  function newJourney(data: NewJourneyForm, source: 'demo' | 'backend', result: Journey['result']) {
    const color = COLORS[journeys.length % COLORS.length]
    const journey: Journey = {
      id: crypto.randomUUID(), name: data.name, color, visible: true, source,
      launch_iso: data.launch_iso, result
    }
    setJourneys(old => [...old, journey])
    setSelectedId(journey.id)
    setClock(new Date(new Date(data.launch_iso).getTime() + result.diagnostics.final_time_s * 1000 * 0.36))
    setPlaying(false)
    setTimeMode('manual')
    setFocusEarthSignal(s => s + 1)
    setFormOpen(false); setDrawerOpen(true); setError('')
  }
  function createDemo(data: NewJourneyForm) {
    newJourney(data, 'demo', createDemoSimulation(data.config, journeys.length + 1))
  }
  async function runBackend(data: NewJourneyForm) {
    if (busy) return
    setBusy(true); setError('')
    try { const result = await runSimulation(data.config); newJourney(data, 'backend', result) }
    catch (e) { setError(e instanceof Error ? e.message : 'Error desconocido al ejecutar la simulación.') }
    finally { setBusy(false) }
  }
  function removeJourney(id: string) {
    const found = journeys.find(j => j.id === id)
    if (!found || !window.confirm(`¿Eliminar el viaje «${found.name}»?`)) return
    setJourneys(old => old.filter(j => j.id !== id))
    if (selectedId === id) { setSelectedId(null); setPlaying(false) }
  }
  function selectJourney(id: string) {
    const journey = journeys.find(j => j.id === id)
    if (!journey) return
    setSelectedId(id)
    if (timeMode === 'manual') setClock(new Date(new Date(journey.launch_iso).getTime() + Math.min(journey.result.diagnostics.final_time_s, journey.result.diagnostics.final_time_s * .3) * 1000))
    setPlaying(false)
    setFocusEarthSignal(s => s + 1)
  }
  function changeMode(mode: TimeMode) { setTimeMode(mode); setPlaying(false); if (mode === 'live') setClock(new Date()) }
  function resetTime() { if (!selected) return; setTimeMode('manual'); setPlaying(false); setClock(new Date(selected.launch_iso)) }
  function togglePlayback() {
    if (!selected || timeMode === 'live') return
    const end = new Date(selected.launch_iso).getTime() + selected.result.diagnostics.final_time_s * 1000
    if (!playing && clock.getTime() >= end) setClock(new Date(selected.launch_iso))
    setPlaying(old => !old)
  }

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand" title="ORBITAL 4B"><span className="brand-logo"><Icon name="orbit" size={26} /></span><div className="brand-type"><div>ORBITAL<span>4B</span></div><small>MISSION CONTROL</small></div></div>
      <div className="header-center"><span className="header-spot" /><span>OBSERVATORIO ESPACIAL</span><span className="header-separator" />SISTEMA SOLAR</div>
      <div className="topbar-right">
        <div className="header-date"><Icon name="calendar" size={15} /><span>{clock.toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' })}</span></div>
        <button className="primary-button create-top" onClick={() => setFormOpen(true)}><Icon name="plus" size={17} /><span>Nueva misión</span></button>
        <button className={`hamburger-button ${drawerOpen ? 'selected' : ''}`} onClick={() => setDrawerOpen(x => !x)} aria-label={drawerOpen ? 'Cerrar menú de viajes' : 'Abrir menú de viajes'} title="Mis viajes"><Icon name={drawerOpen ? 'x' : 'menu'} size={23} />{journeys.length > 0 && <span className="menu-count">{journeys.length}</span>}</button>
      </div>
    </header>
    <main className="main-view">
      <OrbitView date={clock} journeys={journeys} selectedJourneyId={selectedId} onSelectJourney={selectJourney} ephemeris={ephemeris} focusEarthSignal={focusEarthSignal} />
      <div className={`map-overlay-shade ${drawerOpen ? 'shown' : ''}`} />
      <JourneyDrawer open={drawerOpen} journeys={journeys} selectedId={selectedId} date={clock} onClose={() => setDrawerOpen(false)} onNew={() => setFormOpen(true)} onSelect={selectJourney} onToggle={id => setJourneys(old => old.map(j => j.id === id ? { ...j, visible: !j.visible } : j))} onDelete={removeJourney} />
      {selected && <ResultsPanel journey={selected} />}
      <div className="playback-position"><PlaybackControls date={clock} mode={timeMode} onMode={changeMode} journey={selected} playing={playing} onToggle={togglePlayback} speed={speed} onSpeed={setSpeed} onDate={d => { setTimeMode('manual'); setPlaying(false); setClock(d) }} onReset={resetTime} /></div>
      {!selected && <button className="first-mission-button" onClick={() => setFormOpen(true)}><Icon name="rocket" size={18} />Comenzar una misión <Icon name="arrow-right" size={17} /></button>}
    </main>
    {error && <div role="alert" className="toast-error"><Icon name="alert" size={19} /><span>{error}</span><button onClick={() => setError('')} aria-label="Cerrar error"><Icon name="x" size={15} /></button></div>}
    <SimulationForm open={formOpen} busy={busy} onClose={() => setFormOpen(false)} onDemo={createDemo} onBackend={runBackend} />
  </div>
}
