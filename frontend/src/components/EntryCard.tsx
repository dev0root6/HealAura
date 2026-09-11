import { useState } from 'react'
import { correctEntry } from '../api'
import type { Entry } from '../api'

interface EntryCardProps {
  entry: Entry
  onUpdated: (entry: Entry) => void
}

const TYPE_LABELS: Record<string, string> = {
  memory: 'Memory',
  event: 'Event',
  task: 'Task',
}

const SENTIMENT_LABELS: Record<string, string> = {
  positive: 'Positive',
  negative: 'Negative',
  neutral: 'Neutral',
  mixed: 'Mixed',
}

const TYPES = Object.keys(TYPE_LABELS)
const SENTIMENTS = Object.keys(SENTIMENT_LABELS)

export default function EntryCard({ entry, onUpdated }: EntryCardProps) {
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const type = entry.corrected_type ?? entry.entry_type
  const sentiment = entry.corrected_sentiment ?? entry.sentiment

  async function apply(correction: { corrected_type?: string; corrected_sentiment?: string }) {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      onUpdated(await correctEntry(entry.id, correction))
      setEditing(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className={`entry-card${entry.user_confirmed ? ' confirmed' : ''}`}>
      <p className="segment-text">{entry.segment_text}</p>
      <div className="tags">
        <span className={`tag type-${type}`}>{TYPE_LABELS[type] ?? type}</span>
        <span className={`tag sentiment-${sentiment}`}>
          {SENTIMENT_LABELS[sentiment] ?? sentiment}
        </span>
        {entry.person && <span className="tag person">👤 {entry.person}</span>}
        {entry.event_date && (
          <span className="tag date">
            📅 {entry.event_date}
            {entry.event_time ? ` ${entry.event_time}` : ''}
          </span>
        )}
        {entry.is_fallback && (
          <span className="tag unclassified">Unclassified — please review</span>
        )}
        {entry.user_confirmed === 1 && <span className="tag confirmed-tag">✓ Confirmed</span>}
      </div>

      {editing ? (
        <div className="correct-panel">
          <div className="correct-row">
            <span className="correct-label">Type</span>
            {TYPES.map((t) => (
              <button
                key={t}
                type="button"
                disabled={busy || t === type}
                onClick={() => apply({ corrected_type: t })}
              >
                {TYPE_LABELS[t]}
              </button>
            ))}
          </div>
          <div className="correct-row">
            <span className="correct-label">Sentiment</span>
            {SENTIMENTS.map((s) => (
              <button
                key={s}
                type="button"
                disabled={busy || s === sentiment}
                onClick={() => apply({ corrected_sentiment: s })}
              >
                {SENTIMENT_LABELS[s]}
              </button>
            ))}
          </div>
          <button type="button" className="link" onClick={() => setEditing(false)}>
            Cancel
          </button>
        </div>
      ) : (
        <div className="card-actions">
          {entry.user_confirmed !== 1 && (
            <button type="button" disabled={busy} onClick={() => apply({})}>
              Looks right
            </button>
          )}
          <button type="button" className="link" disabled={busy} onClick={() => setEditing(true)}>
            Fix this
          </button>
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </li>
  )
}
