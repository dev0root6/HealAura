import { useEffect, useState } from 'react'
import { MailCheck, User } from 'lucide-react'
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
    <>
    <p className="muted small reminder-note">
      You'll get an email 1 hour before (or at 8 AM, if there's no time).
    </p>
    <ul className="reminder-list">
      {events.map((event) => (
        <li key={event.id} className="reminder-card">
          <span className="reminder-when">{formatWhen(event)}</span>
          <span className="reminder-text">{event.segment_text}</span>
          {event.person && <span className="tag person"><User size={13} aria-hidden="true" /> {event.person}</span>}
          {event.reminder_sent_at && (
            <span className="tag confirmed-tag" title="Email reminder sent">
              <MailCheck size={13} aria-hidden="true" /> Emailed
            </span>
          )}
        </li>
      ))}
    </ul>
    </>
  )
}
