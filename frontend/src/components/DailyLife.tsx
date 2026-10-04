import { useCallback, useEffect, useState } from 'react'
import { CalendarClock, ChevronLeft, ChevronRight, NotebookPen, RefreshCw, Sparkle } from 'lucide-react'
import { getDayPage } from '../api'
import type { DayResponse } from '../api'

interface DailyLifeProps {
  onWrite: () => void
}

function localToday(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function dayLabel(iso: string): string {
  if (iso === localToday()) return 'Today'
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  })
}

/** "Your daily day life": the day written as a diary page, from what you told HealAura. */
export default function DailyLife({ onWrite }: DailyLifeProps) {
  const [date, setDate] = useState<string | undefined>(undefined)
  const [data, setData] = useState<DayResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (day?: string, refresh = false) => {
    setLoading(true)
    setError(null)
    try {
      setData(await getDayPage(day, refresh))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(date)
  }, [date, load])

  const current = data?.date ?? localToday()
  // Browse between days that have entries (plus today).
  const days = Array.from(new Set([localToday(), ...(data?.days ?? [])])).sort().reverse()
  const idx = days.indexOf(current)
  const older = idx >= 0 && idx < days.length - 1 ? days[idx + 1] : undefined
  const newer = idx > 0 ? days[idx - 1] : undefined
  const page = data?.page

  return (
    <section className="daily">
      <div className="daily-head">
        <h2>
          <NotebookPen size={20} aria-hidden="true" /> Your daily day life
        </h2>
        <div className="day-nav">
          <button
            type="button"
            className="icon-btn"
            onClick={() => setDate(older)}
            disabled={!older || loading}
            aria-label="Earlier day"
          >
            <ChevronLeft size={18} />
          </button>
          <span className="day-label">{dayLabel(current)}</span>
          <button
            type="button"
            className="icon-btn"
            onClick={() => setDate(newer)}
            disabled={!newer || loading}
            aria-label="Later day"
          >
            <ChevronRight size={18} />
          </button>
        </div>
      </div>
      <p className="muted small">
        HealAura writes your diary for you, from what you told it. It updates as your day goes on.
      </p>

      {error && <p className="error">{error}</p>}

      {loading && (
        <div className="diary-page glass loading-page" aria-busy="true">
          <p className="muted">Writing your page…</p>
          <span className="skeleton w80" />
          <span className="skeleton w95" />
          <span className="skeleton w70" />
          <span className="skeleton w90" />
        </div>
      )}

      {!loading && !page && !error && (
        <div className="diary-page glass empty-page">
          <p>Nothing written {current === localToday() ? 'today' : 'that day'} yet.</p>
          {current === localToday() && (
            <button type="button" className="primary" onClick={onWrite}>
              Tell HealAura about your day
            </button>
          )}
        </div>
      )}

      {!loading && page && (
        <article className="diary-page glass">
          <header className="diary-title">
            <h3>{page.title}</h3>
            {page.mood && <span className="mood-chip">{page.mood}</span>}
          </header>
          {page.body.split(/\n{2,}/).map((para, i) => (
            <p key={i} className="diary-body">
              {para}
            </p>
          ))}

          {page.highlights.length > 0 && (
            <div className="diary-list">
              <h4>
                <Sparkle size={14} aria-hidden="true" /> Moments worth keeping
              </h4>
              <ul>
                {page.highlights.map((h) => (
                  <li key={h}>{h}</li>
                ))}
              </ul>
            </div>
          )}
          {page.looking_ahead.length > 0 && (
            <div className="diary-list">
              <h4>
                <CalendarClock size={14} aria-hidden="true" /> Coming up
              </h4>
              <ul>
                {page.looking_ahead.map((h) => (
                  <li key={h}>{h}</li>
                ))}
              </ul>
            </div>
          )}

          <footer className="diary-foot muted small">
            From {page.entry_count} {page.entry_count === 1 ? 'entry' : 'entries'} · written{' '}
            {new Date(page.updated_at).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}
            <button type="button" className="link" onClick={() => load(current, true)}>
              <RefreshCw size={13} aria-hidden="true" className="inline-icon" /> Rewrite
            </button>
          </footer>
        </article>
      )}
    </section>
  )
}
