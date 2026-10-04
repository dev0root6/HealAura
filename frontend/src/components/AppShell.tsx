import { useCallback, useEffect, useState } from 'react'
import {
  ChartSpline,
  Heart,
  HeartHandshake,
  LogOut,
  MessageCircleHeart,
  Users,
  Volume2,
  VolumeX,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { getEntries, getMessages, submitEntry } from '../api'
import type { Entry, EntryResponse, Message, User } from '../api'
import Conversation from './Conversation'
import Trends from './Trends'
import EntryInput from './EntryInput'
import ReminderList from './ReminderList'
import Friends from './Friends'
import Counsellors from './Counsellors'
import Community from './Community'
import { useVoiceReply } from '../hooks/useVoiceReply'
import Logo from './Logo'

type Tab = 'ai' | 'trends' | 'community' | 'counsellors' | 'friends'

interface AppShellProps {
  user: User
  onLogout: () => void
}

export default function AppShell({ user, onLogout }: AppShellProps) {
  const tabs: { id: Tab; label: string; icon: LucideIcon }[] = [
    { id: 'ai', label: 'Talk with AI', icon: MessageCircleHeart },
    { id: 'trends', label: 'My trends', icon: ChartSpline },
    { id: 'community', label: 'Community', icon: Users },
    { id: 'counsellors', label: 'Counsellors', icon: HeartHandshake },
    { id: 'friends', label: 'Close friends', icon: Heart },
  ]

  const [tab, setTab] = useState<Tab>('ai')
  const [entries, setEntries] = useState<Entry[]>([])
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [eventsKey, setEventsKey] = useState(0)
  const voice = useVoiceReply()

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
    const userTurn: Message = {
      id: response.entries[0]?.message_id ?? `local-${response.reply.id}`,
      role: 'user',
      content: rawText,
      kind: 'entry',
      needs_support: false,
      crisis: false,
      language_code: response.reply.language_code,
      created_at: response.reply.created_at,
    }
    setMessages((prev) => [...prev, userTurn, response.reply])
    setEntries((prev) => [...prev, ...response.entries])
    setEventsKey((k) => k + 1)
    voice.play(response.reply)
  }

  function handleUpdated(updated: Entry) {
    setEntries((prev) => prev.map((e) => (e.id === updated.id ? updated : e)))
    setEventsKey((k) => k + 1)
  }

  function handleSuggestion(message: Message) {
    setMessages((prev) => [...prev, message])
    voice.play(message)
  }

  return (
    <div className="app">
      <div className="glow" aria-hidden="true" />
      <header>
        <div>
          <h1 className="brand-lockup">
            <Logo size={40} />
            HealAura
          </h1>
          <p className="subtitle">Hi, {user.username} · a softer place to land</p>
        </div>
        <div className="header-actions">
          {tab === 'ai' && (
            <>
              <button
                type="button"
                className={`voice-toggle${voice.enabled ? ' on' : ''}`}
                onClick={voice.toggle}
                aria-pressed={voice.enabled}
              >
                {voice.enabled ? (
                  <Volume2 size={16} aria-hidden="true" />
                ) : (
                  <VolumeX size={16} aria-hidden="true" />
                )}
                {voice.enabled ? 'Voice on' : 'Voice off'}
              </button>
              {voice.enabled && voice.voices.length > 0 && (
                <select
                  className="voice-select"
                  value={voice.voice}
                  onChange={(e) => voice.setVoice(e.target.value)}
                  aria-label="Reply voice"
                >
                  {(['Indian', 'International'] as const).map((family) => (
                    <optgroup
                      key={family}
                      label={family === 'Indian' ? 'Indian · all languages' : 'International · English'}
                    >
                      {voice.voices
                        .filter((v) => v.family === family)
                        .map((v) => (
                          <option key={v.id} value={v.id} disabled={!v.available}>
                            {v.label} ({v.gender === 'f' ? 'female' : 'male'})
                            {v.available ? '' : ' · not enabled yet'}
                          </option>
                        ))}
                    </optgroup>
                  ))}
                </select>
              )}
            </>
          )}
          <button type="button" className="voice-toggle" onClick={onLogout}>
            <LogOut size={16} aria-hidden="true" />
            Sign out
          </button>
        </div>
      </header>

      <nav className="tabs glass" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            aria-label={t.label}
            className={`tab${tab === t.id ? ' active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            <t.icon className="tab-icon" size={18} aria-hidden="true" />
            <span className="tab-label">{t.label}</span>
          </button>
        ))}
      </nav>

      <main>
        {tab === 'ai' && (
          <>
            <section>
              <h2>Today</h2>
              {loadError && <p className="error">Could not load today: {loadError}</p>}
              <Conversation
                messages={messages}
                entries={entries}
                busy={loading}
                onUpdated={handleUpdated}
                onSuggestion={handleSuggestion}
                onOpenTab={setTab}
              />
            </section>
            <EntryInput onSubmit={submitEntry} onSubmitted={handleSubmitted} />
            <section>
              <h2>Reminders</h2>
              <ReminderList refreshKey={eventsKey} />
            </section>
          </>
        )}
        {tab === 'trends' && <Trends />}
        {tab === 'community' && <Community />}
        {tab === 'counsellors' && <Counsellors />}
        {tab === 'friends' && <Friends />}
      </main>
    </div>
  )
}
