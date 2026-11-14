import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'
import { ApiError, requestOptimizedTransfer, requestRoundTripTransfer } from './api/transfers'
import Icon from './components/Icon'
import PlaybackControls from './components/PlaybackControls'
import TradeoffChart from './components/TradeoffChart'
import TransferForm from './components/TransferForm'
import TransferSummary from './components/TransferSummary'
import TransferView from './components/TransferView'
import type { MissionResponse, MissionSubmitPayload } from './types/transfer'
import { stateAt } from './utils/transfer'

export default function App() {
  const [result, setResult] = useState<MissionResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(21600)
  const pending = useRef<AbortController | null>(null)

  const transfer = result?.status === 'ok' ? result : null
  const noFeasible = result?.status === 'no_feasible_solution' ? result : null
  const duration = transfer
    ? (transfer.kind === 'round_trip' ? transfer.total_duration_s : transfer.duration_s)
    : 0
  const state = useMemo(() => (transfer ? stateAt(transfer.samples, time) : null), [transfer, time])

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

  async function calculate(mission: MissionSubmitPayload) {
    pending.current?.abort()
    const controller = new AbortController()
    pending.current = controller
    setBusy(true); setError(''); setPlaying(false)
    try {
      const response =
        mission.kind === 'one_way'
          ? await requestOptimizedTransfer(mission.payload, controller.signal)
          : await requestRoundTripTransfer(mission.payload, controller.signal)
      setResult(response); setTime(0)
    } catch (e) {
      if (controller.signal.aborted) return
      setError(e instanceof ApiError || e instanceof Error ? e.message : 'Error desconocido al calcular la misión.')
    } finally {
      if (pending.current === controller) { pending.current = null; setBusy(false) }
    }
  }

  function cancel() { pending.current?.abort(); pending.current = null; setBusy(false) }
  function toggle() {
    if (!playing && time >= duration) setTime(0)
    setPlaying(p => !p)
  }

  return <div className="app-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-logo"><Icon name="orbit" size={24} /></span>
        <div className="brand-type"><div>ORBITAL<span>4B</span></div><small>PLANIFICADOR CISLUNAR TIERRA–LUNA</small></div></div>
    </header>
    <main className="layout">
      <section className="side-panel">
        <TransferForm busy={busy} onSubmit={calculate} onCancel={cancel} />
        {error && <div role="alert" className="error-box"><Icon name="alert" size={17} /><span>{error}</span>
          <button onClick={() => setError('')} aria-label="Cerrar error"><Icon name="x" size={14} /></button></div>}
        {noFeasible && <aside className="no-feasible-box" role="status">
          <h2><Icon name="alert" size={16} />Sin solución factible</h2>
          {noFeasible.kind === 'one_way' ? (
            <p>Límite pedido: {(noFeasible.max_duration_s / 86400).toLocaleString('es-ES', { maximumFractionDigits: 2 })} días · Dominio mínimo: {(noFeasible.min_search_duration_s / 86400).toLocaleString('es-ES', { maximumFractionDigits: 2 })} días</p>
          ) : (
            <p>Duración máxima pedida: {(noFeasible.max_total_duration_s / 86400).toLocaleString('es-ES', { maximumFractionDigits: 2 })} días</p>
          )}
          <ul>{noFeasible.reasons.map((reason, idx) => <li key={idx}>{reason}</li>)}</ul>
        </aside>}
        {transfer && state && <TransferSummary transfer={transfer} state={state} />}
        {result?.kind === 'one_way' && <TradeoffChart
          tradeoff={result.tradeoff}
          maxDurationS={result.max_duration_s}
          validated={transfer?.kind === 'one_way' ? { duration_s: transfer.duration_s, total_delta_v_m_s: transfer.total_delta_v_m_s } : undefined}
        />}
      </section>
      <section className="stage">
        {transfer && state ? <>
          <TransferView transfer={transfer} state={state} />
          <PlaybackControls start={new Date(transfer.date)} duration={duration} time={time} playing={playing} speed={speed}
            onToggle={toggle} onReset={() => { setPlaying(false); setTime(0) }}
            onTime={t => { setPlaying(false); setTime(t) }} onSpeed={setSpeed} />
        </> : noFeasible ? <div className="stage-empty no-feasible-stage">
          <Icon name="alert" size={40} />
          <p>No existe trayectoria validada dentro del tiempo máximo especificado.</p>
          <small>Amplía el tiempo máximo de vuelo o revisa las razones en el panel izquierdo.</small>
        </div> : <div className="stage-empty">
          <Icon name={busy ? 'clock' : 'globe'} size={40} />
          <p>{busy ? 'Consultando NASA/JPL Horizons y propagando la trayectoria…' : 'Elige el perfil de misión y pulsa «Calcular».'}</p>
        </div>}
      </section>
    </main>
  </div>
}