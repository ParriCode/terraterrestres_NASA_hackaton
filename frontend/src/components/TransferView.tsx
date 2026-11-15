import { useEffect, useState } from 'react'
import type { TransferResponse, TransferState } from '../types/transfer'
import { getEarthMoonEphemeris, getSunDirection } from '../api/ephemerides'
import type { EarthMoonEphemeris, SunDirectionEphemeris } from '../api/ephemerides'
import TransferView2D from './TransferView2D'
import TransferView3D from './TransferView3D'

export type ViewMode = '2d' | '3d'
type Props = {
  date: Date; transfer: TransferResponse | null; state: TransferState | null; time: number
  visible?: boolean; color?: string; onSolar: () => void; mode: ViewMode
}
/** Mantener la selección y el reloj en App: alternar visor no recalcula trayectorias. */
export default function TransferView({ date, transfer, state, time, mode, visible, color, onSolar }: Props) {
  const dateIso = date.toISOString()
  const [previewResult, setPreviewResult] = useState<{
    key: string; data: EarthMoonEphemeris | null; error: string
  } | null>(null)
  const [sunResult, setSunResult] = useState<{
    key: string; data: SunDirectionEphemeris | null; error: string
  } | null>(null)
  // La dirección solar cambia lentamente: consultar una vez por día UTC, no cada fotograma.
  const sunDateKey = `${dateIso.slice(0, 10)}T12:00:00.000Z`
  const sun = sunResult?.key === sunDateKey ? sunResult.data : null
  const sunError = sunResult?.key === sunDateKey ? sunResult.error : ''

  useEffect(() => {
    if (transfer || mode !== '3d') return
    const ctrl = new AbortController()
    const timer = setTimeout(() => {
      getEarthMoonEphemeris(new Date(dateIso), ctrl.signal)
        .then(data => setPreviewResult({ key: dateIso, data, error: '' }))
        .catch(error => {
          if (!ctrl.signal.aborted) setPreviewResult({ key: dateIso, data: null,
            error: error instanceof Error ? error.message : 'Sin efemérides JPL' })
        })
    }, 450)
    return () => { clearTimeout(timer); ctrl.abort() }
  }, [dateIso, transfer, mode])

  useEffect(() => {
    const ctrl = new AbortController()
    const timer = setTimeout(() => {
      getSunDirection(new Date(sunDateKey), ctrl.signal)
        .then(data => setSunResult({ key: sunDateKey, data, error: '' }))
        .catch(error => { if (!ctrl.signal.aborted) setSunResult({ key: sunDateKey,
          data: null, error: error instanceof Error ? error.message : 'Sin dirección JPL' }) })
    }, 450)
    return () => { clearTimeout(timer); ctrl.abort() }
  }, [sunDateKey])

  if (mode === '2d') return <TransferView2D date={date} transfer={transfer} state={state} time={time}
    visible={visible} color={color} onSolar={onSolar} sun={sun} sunError={sunError} />
  return <TransferView3D date={date} transfer={transfer} state={state} time={time} visible={visible}
    color={color} onSolar={onSolar} preview={previewResult?.key === dateIso ? previewResult.data : null}
    previewError={previewResult?.key === dateIso ? previewResult.error : ''} sun={sun} sunError={sunError} />
}
