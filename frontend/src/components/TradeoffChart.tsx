import type { TradeoffPoint } from '../types/transfer'

type Props = {
    tradeoff: TradeoffPoint[]
    maxDurationS: number
    validated?: { duration_s: number; total_delta_v_m_s: number }
}

const WIDTH = 320
const HEIGHT = 185
const PAD = { top: 14, right: 16, bottom: 32, left: 46 }

const fmtDays = (s: number) => (s / 86400).toLocaleString('es-ES', { maximumFractionDigits: 1 })
const fmtKmS = (ms: number) => (ms / 1000).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export default function TradeoffChart({ tradeoff, maxDurationS, validated }: Props) {
    if (!tradeoff.length) {
        return <section className="tradeoff-panel">
            <h3>Curva Δv – tiempo de vuelo</h3>
            <p className="tradeoff-empty">Sin puntos en el cribado Lambert para el límite solicitado ({fmtDays(maxDurationS)} días).</p>
        </section>
    }

    const timesDays = tradeoff.map(p => p.duration_s / 86400)
    const dvsKmS = tradeoff.map(p => p.estimated_total_delta_v_m_s / 1000)
    if (validated) {
        timesDays.push(validated.duration_s / 86400)
        dvsKmS.push(validated.total_delta_v_m_s / 1000)
    }

    const minX = Math.min(...timesDays)
    const maxX = Math.max(...timesDays, minX + 0.5)
    const rawMinY = Math.min(...dvsKmS)
    const rawMaxY = Math.max(...dvsKmS)
    const spanY = Math.max(0.2, rawMaxY - rawMinY)
    const minY = Math.max(0, rawMinY - spanY * 0.15)
    const maxY = rawMaxY + spanY * 0.15

    const plotW = WIDTH - PAD.left - PAD.right
    const plotH = HEIGHT - PAD.top - PAD.bottom
    const sx = (days: number) => PAD.left + ((days - minX) / (maxX - minX)) * plotW
    const sy = (dvKmS: number) => PAD.top + (1 - (dvKmS - minY) / (maxY - minY)) * plotH

    const linePoints = tradeoff
        .map(p => `${sx(p.duration_s / 86400).toFixed(1)},${sy(p.estimated_total_delta_v_m_s / 1000).toFixed(1)}`)
        .join(' ')

    const yTicks = [minY, (minY + maxY) / 2, maxY]
    const xTicks = [minX, (minX + maxX) / 2, maxX]

    return <section className="tradeoff-panel" aria-label="Curva delta-v frente a tiempo de vuelo">
        <h3>Curva Δv – tiempo de vuelo</h3>
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="tradeoff-svg">
            {yTicks.map((y, idx) => {
                const py = sy(y)
                return <g key={idx}>
                    <line x1={PAD.left} y1={py} x2={WIDTH - PAD.right} y2={py} className="chart-grid" />
                    <text x={PAD.left - 6} y={py + 3} textAnchor="end" className="chart-tick">{y.toFixed(2)}</text>
                </g>
            })}
            {xTicks.map((x, idx) => {
                const px = sx(x)
                return <text key={idx} x={px} y={HEIGHT - 12} textAnchor="middle" className="chart-tick">{x.toFixed(1)} d</text>
            })}
            <line x1={PAD.left} y1={PAD.top} x2={PAD.left} y2={HEIGHT - PAD.bottom} className="chart-axis" />
            <line x1={PAD.left} y1={HEIGHT - PAD.bottom} x2={WIDTH - PAD.right} y2={HEIGHT - PAD.bottom} className="chart-axis" />
            <text x={12} y={PAD.top + plotH / 2} transform={`rotate(-90 12 ${PAD.top + plotH / 2})`} textAnchor="middle" className="chart-label">Δv (km/s)</text>

            {tradeoff.length > 1 && <polyline points={linePoints} className="chart-line-lambert" />}
            {tradeoff.map((p, idx) => (
                <circle
                    key={idx}
                    cx={sx(p.duration_s / 86400)}
                    cy={sy(p.estimated_total_delta_v_m_s / 1000)}
                    r={2.8}
                    className="chart-dot-lambert"
                >
                    <title>{`${fmtDays(p.duration_s)} d · Cribado Lambert: ${fmtKmS(p.estimated_total_delta_v_m_s)} km/s`}</title>
                </circle>
            ))}
            {validated && (
                <g>
                    <circle
                        cx={sx(validated.duration_s / 86400)}
                        cy={sy(validated.total_delta_v_m_s / 1000)}
                        r={6}
                        className="chart-dot-validated-halo"
                    />
                    <circle
                        cx={sx(validated.duration_s / 86400)}
                        cy={sy(validated.total_delta_v_m_s / 1000)}
                        r={3.8}
                        className="chart-dot-validated"
                    >
                        <title>{`Validado DOP853: ${fmtDays(validated.duration_s)} d · ${fmtKmS(validated.total_delta_v_m_s)} km/s`}</title>
                    </circle>
                </g>
            )}
        </svg>
        <div className="tradeoff-legend">
            <span><i className="legend-lambert" />Cribado Lambert (estimación 2 cuerpos)</span>
            {validated && <span><i className="legend-validated" />Óptimo validado (DOP853)</span>}
        </div>
    </section>
}
