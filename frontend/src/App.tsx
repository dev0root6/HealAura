import { useCallback, useEffect, useState } from 'react'
import { getEntries, submitEntry } from './api'
import type { Entry } from './api'
import EntryInput from './components/EntryInput'
import EntryList from './components/EntryList'
import ReminderList from './components/ReminderList'

export default function App() {
  const [entries, setEntries] = useState<Entry[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [eventsKey, setEventsKey] = useState(0)

  const refresh = useCallback(async () => {
    try {
      setEntries(await getEntries())
      setLoadError(null)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  function handleSubmitted(newEntries: Entry[]) {
    setEntries((prev) => [...newEntries, ...prev])
    setEventsKey((k) => k + 1)
  }

  function handleUpdated(updated: Entry) {
    setEntries((prev) => prev.map((e) => (e.id === updated.id ? updated : e)))
    setEventsKey((k) => k + 1)
  }

  return (
    <div className="app">
      <header>
        <h1>HealAura</h1>
        <p className="subtitle">Daily reflection journal</p>
      </header>
      <main>
        <EntryInput onSubmit={submitEntry} onSubmitted={handleSubmitted} />
        <section>
          <h2>Today</h2>
          {loadError && <p className="error">Could not load entries: {loadError}</p>}
          <EntryList entries={entries} busy={loading} onUpdated={handleUpdated} />
        </section>
        <section>
          <h2>Reminders</h2>
          <ReminderList refreshKey={eventsKey} />
        </section>
      </main>
    </div>
  )
}