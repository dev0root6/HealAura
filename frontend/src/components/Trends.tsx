import { useEffect, useRef, useState } from 'react'
import { TrendingDown, TrendingUp } from 'lucide-react'
import { getTrends } from '../api'
import type { DayTrend, Trends as TrendsData } from '../api'

type Sentiment = 'positive' | 'neutral' | 'mixed' | 'negative'

// Stacked bottom-to-top in this order. Colours were checked with the dataviz
// palette validator; neutral is a deliberate gray midpoint, and every series
// also carries a legend label, a tooltip and the table view, so identity never
// rests on colour alone.
const SERIES: { key: Sentiment; label: string; color: string }[] = [
  { key: 'positive', label: 'Positive', color: '#2a9d6e' },
  { key: 'neutral', label: 'Neutral', color: '#a9a29c' },
  { key: 'mixed', label: 'Mixed', color: '#9b5cc4' },
  { key: 'negative', label: 'Negative', color: '#e0505f' },
]

const RANGES = [14, 30, 90]

// Chart geometry in CSS pixels: the width follows the container (see
// useWidth) so axis text stays readable on phones instead of being scaled down.
const H = 180
const PAD = { top: 10, right: 8, bottom: 22, left: 30 }
const GAP = 2 // surface gap between stacked segments

function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`)
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

/** Track an element's content width; charts redraw at their real size. */
function useWidth<T extends HTMLElement>(fallback = 640) {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(fallback)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(280, Math.round(e.contentRect.width))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, width] as const
}

function pct(v: number | null): string {
  return v === null ? '—' : `${Math.round(v * 100)}%`
}

function Tooltip({ day, x, W }: { day: DayTrend; x: number; W: number }) {
  return (
    // Clamped so the tooltip never hangs off either edge of the chart.
    <div className="trend-tip" style={{ left: `${Math.min(82, Math.max(18, (x / W) * 100))}%` }}>
      <strong>{shortDate(day.day)}</strong>
      {day.total === 0 ? (
        <span className="muted">No entries</span>
      ) : (
        SERIES.filter((s) => day[s.key] > 0).map((s) => (
          <span key={s.key}>
            <i className="swatch" style={{ background: s.color }} /> {s.label}: {day[s.key]}
          </span>
        ))
      )}
      {day.smoothed_negative !== null && <span>Heaviness: {pct(day.smoothed_negative)}</span>}
    </div>
  )
}

function StackedBars({ days }: { days: DayTrend[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const [ref, W] = useWidth<HTMLDivElement>()
  const maxTotal = Math.max(1, ...days.map((d) => d.total))
  const plotW = W - PAD.left - PAD.right
  const plotH = H - PAD.top - PAD.bottom
  const slot = plotW / days.length
  const barW = Math.max(2, Math.min(18, slot * 0.7))
  const y = (v: number) => PAD.top + plotH - (v / maxTotal) * plotH
  const ticks = [0, Math.ceil(maxTotal / 2), maxTotal].filter((v, i, a) => a.indexOf(v) === i)
  const labelEvery = Math.ceil(days.length / Math.max(3, Math.floor(W / 90)))

  return (
    <div className="trend-chart" ref={ref}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Segments per day by sentiment">
        {ticks.map((t) => (
          <g key={t}>
            <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} />
            <text className="axis" x={PAD.left - 6} y={y(t) + 3} textAnchor="end">
              {t}
            </text>
          </g>
        ))}
        {days.map((d, i) => {
          const cx = PAD.left + slot * i + slot / 2
          let base = d.total
          const parts = SERIES.filter((s) => d[s.key] > 0)
          return (
            <g key={d.day}>
              {[...parts].reverse().map((s, j) => {
                // Draw top-down so the topmost segment gets the rounded end.
                const top = y(base)
                base -= d[s.key]
                const h = Math.max(1, y(base) - top - (base > 0 ? GAP : 0))
                return (
                  <rect
                    key={s.key}
                    x={cx - barW / 2}
                    y={top}
                    width={barW}
                    height={h}
                    rx={j === 0 ? Math.min(4, barW / 2) : 0}
                    fill={s.color}
                    opacity={hover === null || hover === i ? 1 : 0.45}
                  />
                )
              })}
              {i % labelEvery === 0 && (
                <text className="axis" x={cx} y={H - 6} textAnchor="middle">
                  {shortDate(d.day)}
                </text>
              )}
              {/* Hit target: the whole column, larger than the bar itself. */}
              <rect
                x={PAD.left + slot * i}
                y={PAD.top}
                width={slot}
                height={plotH}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
                onTouchStart={() => setHover(i)}
              />
            </g>
          )
        })}
      </svg>
      {hover !== null && <Tooltip day={days[hover]} x={PAD.left + slot * hover + slot / 2} W={W} />}
    </div>
  )
}

function HeavinessLine({ days }: { days: DayTrend[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const [ref, W] = useWidth<HTMLDivElement>()
  const plotW = W - PAD.left - PAD.right
  const plotH = H - PAD.top - PAD.bottom
  const slot = plotW / days.length
  const x = (i: number) => PAD.left + slot * i + slot / 2
  const y = (v: number) => PAD.top + plotH - v * plotH
  const points = days
    .map((d, i) => (d.smoothed_negative === null ? null : `${x(i)},${y(d.smoothed_negative)}`))
    .filter(Boolean)
  const labelEvery = Math.ceil(days.length / Math.max(3, Math.floor(W / 90)))

  return (
    <div className="trend-chart" ref={ref}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Smoothed share of negative segments">
        {[0, 0.5, 1].map((t) => (
          <g key={t}>
            <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} />
            <text className="axis" x={PAD.left - 6} y={y(t) + 3} textAnchor="end">
              {t * 100}%
            </text>
          </g>
        ))}
        {days.map(
          (d, i) =>
            i % labelEvery === 0 && (
              <text key={d.day} className="axis" x={x(i)} y={H - 6} textAnchor="middle">
                {shortDate(d.day)}
              </text>
            ),
        )}
        {points.length > 1 && (
          <polyline points={points.join(' ')} fill="none" stroke="#e0505f" strokeWidth={2} />
        )}
        {hover !== null && days[hover].smoothed_negative !== null && (
          <>
            <line className="crosshair" x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + plotH} />
            <circle
              cx={x(hover)}
              cy={y(days[hover].smoothed_negative as number)}
              r={4}
              fill="#e0505f"
              stroke="var(--chart-surface)"
              strokeWidth={2}
            />
          </>
        )}
        {days.map((d, i) => (
          <rect
            key={d.day}
            x={PAD.left + slot * i}
            y={PAD.top}
            width={slot}
            height={plotH}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
            onTouchStart={() => setHover(i)}
          />
        ))}
      </svg>
      {hover !== null && <Tooltip day={days[hover]} x={x(hover)} W={W} />}
    </div>
  )
}

export default function Trends() {
  const [range, setRange] = useState(30)
  const [data, setData] = useState<TrendsData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    getTrends(range)
      .then((d) => !cancelled && setData(d))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : String(err)))
    return () => {
      cancelled = true
    }
  }, [range])

  const days = data?.days ?? []
  const written = days.filter((d) => d.total > 0)
  const totalSegments = data ? Object.values(data.totals).reduce((a, b) => a + b, 0) : 0
  const latest = [...days].reverse().find((d) => d.smoothed_negative !== null)
  const weekAgo = days.length > 7 ? days[days.length - 8].smoothed_negative : null
  const change =
    latest?.smoothed_negative != null && weekAgo != null ? latest.smoothed_negative - weekAgo : null

  return (
    <section className="trends">
      <div className="trends-head">
        <h2>My trends</h2>
        <div className="range-picker" role="group" aria-label="Time range">
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              className={`chip${r === range ? ' active' : ''}`}
              aria-pressed={r === range}
              onClick={() => setRange(r)}
            >
              {r} days
            </button>
          ))}
        </div>
      </div>
      <p className="muted trends-intro">
        A look back, not a diagnosis. Counts use your corrections wherever you made them.
      </p>

      {error && <p className="error">Could not load trends: {error}</p>}
      {!data && !error && <p className="muted">Loading…</p>}

      {data && written.length === 0 && (
        <p className="muted">No entries in this period yet. Your trends will show up here.</p>
      )}

      {data && written.length > 0 && (
        <>
          <div className="stat-row">
            <div className="stat glass">
              <span className="stat-value">{written.length}</span>
              <span className="stat-label">days you wrote</span>
            </div>
            <div className="stat glass">
              <span className="stat-value">{pct(totalSegments ? data.totals.negative / totalSegments : null)}</span>
              <span className="stat-label">of moments were heavy</span>
            </div>
            <div className="stat glass">
              <span className="stat-value">{pct(latest?.smoothed_negative ?? null)}</span>
              <span className="stat-label">
                heaviness lately
                {change !== null && Math.abs(change) >= 0.05 && (
                  <>
                    {' · '}
                    {change > 0 ? (
                      <TrendingUp size={13} aria-hidden="true" />
                    ) : (
                      <TrendingDown size={13} aria-hidden="true" />
                    )}{' '}
                    {change > 0 ? 'up' : 'down'} vs last week
                  </>
                )}
              </span>
            </div>
          </div>

          <div className="panel glass">
            <h3>What each day held</h3>
            <ul className="legend">
              {SERIES.map((s) => (
                <li key={s.key}>
                  <i className="swatch" style={{ background: s.color }} /> {s.label}
                </li>
              ))}
            </ul>
            <StackedBars days={days} />
          </div>

          <div className="panel glass">
            <h3>Heaviness over time</h3>
            <p className="muted small">
              Share of each day's moments that were negative, smoothed over about a week. Days you
              didn't write keep the last value.
            </p>
            <HeavinessLine days={days} />
          </div>

          <details className="panel glass">
            <summary>Show as a table</summary>
            <table className="trend-table">
              <thead>
                <tr>
                  <th>Day</th>
                  {SERIES.map((s) => (
                    <th key={s.key}>{s.label}</th>
                  ))}
                  <th>Heaviness</th>
                </tr>
              </thead>
              <tbody>
                {written.map((d) => (
                  <tr key={d.day}>
                    <td>{shortDate(d.day)}</td>
                    {SERIES.map((s) => (
                      <td key={s.key}>{d[s.key]}</td>
                    ))}
                    <td>{pct(d.smoothed_negative)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </section>
  )
}
