import { useState } from 'react'
import { askForSuggestion } from '../api'
import type { Entry, Message } from '../api'
import EntryCard from './EntryCard'

interface ConversationProps {
  messages: Message[]
  entries: Entry[]
  busy?: boolean
  onUpdated: (entry: Entry) => void
  onSuggestion: (message: Message) => void
}

/** Cards extracted from one user turn, shown folded under that turn. */
function TurnDetail({
  entries,
  onUpdated,
}: {
  entries: Entry[]
  onUpdated: (entry: Entry) => void
}) {
  const [open, setOpen] = useState(false)
  if (entries.length === 0) return null
  return (
    <div className="turn-detail">
      <button type="button" className="link" onClick={() => setOpen((v) => !v)}>
        {open ? 'Hide' : `What I picked up (${entries.length})`}
      </button>
      {open && (
        <ul className="entry-list">
          {entries.map((entry) => (
            <EntryCard key={entry.id} entry={entry} onUpdated={onUpdated} />
          ))}
        </ul>
      )}
    </div>
  )
}

function UserTurn({
  message,
  entries,
  onUpdated,
  onSuggestion,
}: {
  message: Message
  entries: Entry[]
  onUpdated: (entry: Entry) => void
  onSuggestion: (message: Message) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function ask() {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      onSuggestion(await askForSuggestion(message.content))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className="turn turn-user">
      <p className="turn-text">{message.content}</p>
      <div className="turn-actions">
        <button type="button" className="link" disabled={busy} onClick={ask}>
          {busy ? 'Thinking…' : 'Any suggestion?'}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      <TurnDetail entries={entries} onUpdated={onUpdated} />
    </li>
  )
}

export default function Conversation({
  messages,
  entries,
  busy = false,
  onUpdated,
  onSuggestion,
}: ConversationProps) {
  if (busy && messages.length === 0) return <p className="muted">Loading…</p>
  if (messages.length === 0) {
    return <p className="muted">Nothing yet today. Tell me how it went.</p>
  }

  return (
    <ul className="conversation">
      {messages.map((message) =>
        message.role === 'user' ? (
          <UserTurn
            key={message.id}
            message={message}
            entries={entries.filter((e) => e.message_id === message.id)}
            onUpdated={onUpdated}
            onSuggestion={onSuggestion}
          />
        ) : (
          <li
            key={message.id}
            className={`turn turn-assistant${message.kind === 'suggestion' ? ' suggestion' : ''}`}
          >
            <p className="turn-text">{message.content}</p>
            {message.needs_support && (
              <p className="support-nudge">
                Sounds heavy. Talking to someone might help — counselling is coming soon.
              </p>
            )}
          </li>
        ),
      )}
    </ul>
  )
}
