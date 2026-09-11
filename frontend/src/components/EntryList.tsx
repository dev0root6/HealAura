import type { Entry } from '../api'
import EntryCard from './EntryCard'

interface EntryListProps {
  entries: Entry[]
  busy?: boolean
  onUpdated: (entry: Entry) => void
}

export default function EntryList({ entries, busy = false, onUpdated }: EntryListProps) {
  if (busy && entries.length === 0) {
    return <p className="muted">Loading…</p>
  }
  if (entries.length === 0) {
    return <p className="muted">No entries yet — submit your first reflection above.</p>
  }
  return (
    <ul className="entry-list">
      {entries.map((entry) => (
        <EntryCard key={entry.id} entry={entry} onUpdated={onUpdated} />
      ))}
    </ul>
  )
}
