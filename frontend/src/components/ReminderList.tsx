import { useEffect, useState } from 'react'
import { getEvents } from '../api'
import type { Entry } from '../api'

interface ReminderListProps {
  /** Bumped by the parent whenever entries change, to re-fetch events. */
  refreshKey?: number
}

function formatWhen(entry: Entry): string {
  if (!entry.event_date) return ''
  return entry.event_time ? `${entry.event_date} · ${entry.event_time.slice(0, 5)}` : entry.event_date
}

export default function ReminderList({ refreshKey = 0 }: ReminderListProps) {
  const [events, setEvents] = useState<Entry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getEvents()
      .then((data) => {
        if (cancelled) return
        setEvents(data)
        setError(null)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [refreshKey])

  if (error) return <p className="error">Could not load reminders: {error}</p>
  if (loading && events.length === 0) return <p className="muted">Loading…</p>
  if (events.length === 0) return <p className="muted">No upcoming events.</p>

  return (
    <ul className="reminder-list">
      {events.map((event) => (
        <li key={event.id} className="reminder-card">
          <span className="reminder-when">{formatWhen(event)}</span>
          <span className="reminder-text">{event.segment_text}</span>
          {event.person && <span className="tag person">👤 {event.person}</span>}
        </li>
      ))}
    </ul>
  )
}
