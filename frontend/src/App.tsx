import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'
import { ApiError, requestTransfer } from './api/transfers'
import Icon from './components/Icon'
import PlaybackControls from './components/PlaybackControls'
import TransferForm from './components/TransferForm'
import TransferSummary from './components/TransferSummary'
import TransferView from './components/TransferView'
import type { TransferRequest, TransferResponse } from './types/transfer'
import { stateAt } from './utils/transfer'

export default function App() {
  const [transfer, setTransfer] = useState<TransferResponse | null>(null) // solo la última
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(21600)
  const pending = useRef<AbortController | null>(null)

  const duration = transfer?.duration_s ?? 0
  const state = useMemo(() => transfer ? stateAt(transfer.samples, time) : null, [transfer, time])

  // Animación local: solo avanza el tiempo, sin nuevas peticiones
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
    pending.current?.abort()
    const controller = new AbortController()
    pending.current = controller
    setBusy(true); setError(''); setPlaying(false)
    try {
      const result = await requestTransfer(request, controller.signal)
      setTransfer(result); setTime(0)
    } catch (e) {
      if (controller.signal.aborted) return
      setError(e instanceof ApiError || e instanceof Error ? e.message : 'Error desconocido al calcular la transferencia.')
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
        <div className="brand-type"><div>ORBITAL<span>4B</span></div><small>TRANSFERENCIA TIERRA–LUNA</small></div></div>
    </header>
    <main className="layout">
      <section className="side-panel">
        <TransferForm busy={busy} onSubmit={calculate} onCancel={cancel} />
        {error && <div role="alert" className="error-box"><Icon name="alert" size={17} /><span>{error}</span>
          <button onClick={() => setError('')} aria-label="Cerrar error"><Icon name="x" size={14} /></button></div>}
        {transfer && state && <TransferSummary transfer={transfer} state={state} />}
      </section>
      <section className="stage">
        {transfer && state ? <>
          <TransferView transfer={transfer} state={state} />
          <PlaybackControls start={new Date(transfer.date)} duration={duration} time={time} playing={playing} speed={speed}
            onToggle={toggle} onReset={() => { setPlaying(false); setTime(0) }}
            onTime={t => { setPlaying(false); setTime(t) }} onSpeed={setSpeed} />
        </> : <div className="stage-empty">
          <Icon name={busy ? 'clock' : 'globe'} size={40} />
          <p>{busy ? 'Consultando NASA/JPL Horizons y resolviendo la transferencia…' : 'Configura la salida y pulsa «Calcular transferencia».'}</p>
        </div>}
      </section>
    </main>
  </div>
}
