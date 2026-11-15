import { useEffect, useState } from 'react'
import type { TransferResponse, TransferState } from '../types/transfer'
import { getEarthMoonEphemeris, getSunDirection } from '../api/ephemerides'
import type { EarthMoonEphemeris, SunDirectionEphemeris } from '../api/ephemerides'
import TransferView2D from './TransferView2D'
import TransferView3D from './TransferView3D'

export type ViewMode = '2d' | '3d'
type Props = {
  date: Date
  transfer: TransferResponse | null
  state: TransferState | null
  time: number
  visible?: boolean
  color?: string
  mode: ViewMode
}

export default function TransferView({ date, transfer, state, time, mode, visible, color }: Props) {
  // Único origen de datos JPL para las dos vistas. Cambiar 2D/3D no consulta
  // la API, no recalcula la misión y no altera el reloj de reproducción.
  const dateIso = date.toISOString()
  const [previewResult, setPreviewResult] = useState<{
    date: string; data: EarthMoonEphemeris | null; error: string
  } | null>(null)
  const [sunResult, setSunResult] = useState<{
    key: string; data: SunDirectionEphemeris | null; error: string
  } | null>(null)
  const sunDateKey = `${dateIso.slice(0, 10)}T12:00:00.000Z`
  const preview = previewResult?.date === dateIso ? previewResult.data : null
  const previewError = previewResult?.date === dateIso ? previewResult.error : ''
  const sun = sunResult?.key === sunDateKey ? sunResult.data : null
  const sunError = sunResult?.key === sunDateKey ? sunResult.error : ''

  useEffect(() => {
    if (transfer) return
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      getEarthMoonEphemeris(new Date(dateIso), controller.signal)
        .then(data => setPreviewResult({ date: dateIso, data, error: '' }))
        .catch(error => {
          if (!controller.signal.aborted) setPreviewResult({
            date: dateIso, data: null,
            error: error instanceof Error ? error.message : 'No se obtuvieron las efemérides',
          })
        })
    }, 450)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [dateIso, transfer])

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      getSunDirection(new Date(sunDateKey), controller.signal)
        .then(data => setSunResult({ key: sunDateKey, data, error: '' }))
        .catch(error => {
          if (!controller.signal.aborted) setSunResult({
            key: sunDateKey, data: null,
            error: error instanceof Error ? error.message : 'Dirección solar no disponible',
          })
        })
    }, 450)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [sunDateKey])

  const props = { date, transfer, state, time, visible, color, preview, previewError, sun, sunError }
  return mode === '2d' ? <TransferView2D {...props} /> : <TransferView3D {...props} />
}
