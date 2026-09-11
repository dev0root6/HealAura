import { useCallback, useEffect, useState } from 'react'
import { getEntries, getMessages, submitEntry } from './api'
import type { Entry, EntryResponse, Message } from './api'
import Conversation from './components/Conversation'
import EntryInput from './components/EntryInput'
import ReminderList from './components/ReminderList'

export default function App() {
  const [entries, setEntries] = useState<Entry[]>([])
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [eventsKey, setEventsKey] = useState(0)

  const refresh = useCallback(async () => {
    try {
      const [loadedMessages, loadedEntries] = await Promise.all([getMessages(), getEntries()])
      setMessages(loadedMessages)
      setEntries(loadedEntries)
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

  function handleSubmitted(response: EntryResponse, rawText: string) {
    // The user's own turn is echoed optimistically; the reply comes from the
    // server alongside the classified segments.
    const userTurn: Message = {
      id: response.entries[0]?.message_id ?? `local-${response.reply.id}`,
      role: 'user',
      content: rawText,
      kind: 'entry',
      needs_support: false,
      created_at: response.reply.created_at,
    }
    setMessages((prev) => [...prev, userTurn, response.reply])
    setEntries((prev) => [...prev, ...response.entries])
    setEventsKey((k) => k + 1)
  }

  function handleUpdated(updated: Entry) {
    setEntries((prev) => prev.map((e) => (e.id === updated.id ? updated : e)))
    setEventsKey((k) => k + 1)
  }

  function handleSuggestion(message: Message) {
    setMessages((prev) => [...prev, message])
  }

  return (
    <div className="app">
      <header>
        <h1>HealAura</h1>
        <p className="subtitle">Daily reflection journal</p>
      </header>
      <main>
        <section>
          <h2>Today</h2>
          {loadError && <p className="error">Could not load today: {loadError}</p>}
          <Conversation
            messages={messages}
            entries={entries}
            busy={loading}
            onUpdated={handleUpdated}
            onSuggestion={handleSuggestion}
          />
        </section>
        <EntryInput onSubmit={submitEntry} onSubmitted={handleSubmitted} />
        <section>
          <h2>Reminders</h2>
          <ReminderList refreshKey={eventsKey} />
        </section>
      </main>
    </div>
  )
}
