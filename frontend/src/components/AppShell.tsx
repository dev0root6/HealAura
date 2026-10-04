import { useCallback, useEffect, useRef, useState } from 'react'
import {
  BookHeart,
  ChartSpline,
  Heart,
  HeartHandshake,
  LogOut,
  UserRound,
  MessageCircleHeart,
  Users,
  Volume2,
  VolumeX,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { getEntries, getMessages } from '../api'
import type { ChatMode, Entry, EntryResponse, Message, User } from '../api'
import Conversation from './Conversation'
import Trends from './Trends'
import DailyLife from './DailyLife'
import ProfileSetup from './ProfileSetup'
import EntryInput from './EntryInput'
import ReminderList from './ReminderList'
import Friends from './Friends'
import Counsellors from './Counsellors'
import Community from './Community'
import { useVoiceReply } from '../hooks/useVoiceReply'
import Logo from './Logo'

type Tab = 'ai' | 'day' | 'trends' | 'community' | 'counsellors' | 'friends'

const MODE_KEY = 'healaura:chat-mode'

function readMode(): ChatMode {
  try {
    return localStorage.getItem(MODE_KEY) === 'long' ? 'long' : 'short'
  } catch {
    return 'short'
  }
}

interface AppShellProps {
  user: User
  onLogout: () => void
  onUserChange: (user: User) => void
}

const SETUP_SNOOZE_KEY = 'healaura:setup-snoozed'

function setupSnoozed(): boolean {
  try {
    return sessionStorage.getItem(SETUP_SNOOZE_KEY) === '1'
  } catch {
    return false
  }
}

export default function AppShell({ user, onLogout, onUserChange }: AppShellProps) {
  const tabs: { id: Tab; label: string; icon: LucideIcon }[] = [
    { id: 'ai', label: 'Talk with AI', icon: MessageCircleHeart },
    { id: 'day', label: 'Daily life', icon: BookHeart },
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
  const [chatMode, setChatMode] = useState<ChatMode>(readMode)
  const chatScrollRef = useRef<HTMLDivElement>(null)
  const chatPanelRef = useRef<HTMLElement>(null)

  // Fit the chat panel to the space left below it on screen, so the input is
  // always fully visible (the header and banners wrap differently per device).
  useEffect(() => {
    if (tab !== 'ai') return
    const fit = () => {
      const el = chatPanelRef.current
      if (!el) return
      const top = el.getBoundingClientRect().top + window.scrollY
      el.style.height = `${Math.max(380, window.innerHeight - top - 12)}px`
    }
    fit()
    window.addEventListener('resize', fit)
    const ro = new ResizeObserver(fit)
    ro.observe(document.body)
    return () => {
      window.removeEventListener('resize', fit)
      ro.disconnect()
    }
  }, [tab, user.setup_complete])

  // Keep the newest message in view: on first load, on each new turn, and when
  // coming back to the chat tab.
  useEffect(() => {
    const el = chatScrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: messages.length > 2 ? 'smooth' : 'auto' })
  }, [messages.length, tab])
  // Accounts that haven't finished setup (older accounts, or skipped) are asked once per session.
  const [profileOpen, setProfileOpen] = useState(() => !user.setup_complete && !setupSnoozed())

  function closeProfile() {
    setProfileOpen(false)
    if (!user.setup_complete) {
      try {
        sessionStorage.setItem(SETUP_SNOOZE_KEY, '1')
      } catch {
        /* will ask again next load */
      }
    }
  }

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

  function handleSubmitted(response: EntryResponse, rawText: string, options: { live?: boolean } = {}) {
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
    // Live talk always speaks the reply, and waits for it before listening again.
    return voice.play(response.reply, { force: options.live })
  }

  function changeMode(next: ChatMode) {
    setChatMode(next)
    try {
      localStorage.setItem(MODE_KEY, next)
    } catch {
      /* preference just won't persist */
    }
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
          <p className="subtitle">Hi, {user.preferred_name || user.username} · a softer place to land</p>
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
          <button type="button" className="voice-toggle" onClick={() => setProfileOpen(true)}>
            <UserRound size={16} aria-hidden="true" />
            Profile
          </button>
          <button type="button" className="voice-toggle" onClick={onLogout}>
            <LogOut size={16} aria-hidden="true" />
            Sign out
          </button>
        </div>
      </header>

      {!user.setup_complete && !profileOpen && (
        <div className="setup-banner glass" role="status">
          <span>
            <strong>Finish setting up your account:</strong> add your email, the language you speak
            and your interests.
          </span>
          <button type="button" className="primary" onClick={() => setProfileOpen(true)}>
            Set up now
          </button>
        </div>
      )}
      {profileOpen && (
        <ProfileSetup
          user={user}
          onboarding={!user.setup_complete}
          onSaved={(u) => {
            onUserChange(u)
            setProfileOpen(false)
          }}
          onClose={closeProfile}
        />
      )}

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
            {/* The chat scrolls inside this panel; the input stays pinned at its bottom. */}
            <section className="chat-panel" ref={chatPanelRef}>
              <div className="chat-head">
                <h2>Today</h2>
                <div className="chat-options" role="radiogroup" aria-label="Reply style">
              <span className="muted small">Replies:</span>
              {(
                [
                  ['short', 'Short', 'A few words, mostly listening'],
                  ['long', 'Conversation', 'Talks back and asks you questions'],
                ] as const
              ).map(([id, label, hint]) => (
                <button
                  key={id}
                  type="button"
                  role="radio"
                  aria-checked={chatMode === id}
                  className={`chip${chatMode === id ? ' active' : ''}`}
                  onClick={() => changeMode(id)}
                  title={hint}
                >
                  {label}
                </button>
              ))}
                </div>
              </div>
              <div className="chat-scroll" ref={chatScrollRef}>
                {loadError && <p className="error">Could not load today: {loadError}</p>}
                <Conversation
                  messages={messages}
                  entries={entries}
                  busy={loading}
                  onUpdated={handleUpdated}
                  onSuggestion={handleSuggestion}
                  onOpenTab={setTab}
                />
              </div>
              <EntryInput mode={chatMode} onSubmitted={handleSubmitted} />
            </section>
            <section>
              <h2>Reminders</h2>
              <ReminderList refreshKey={eventsKey} />
            </section>
          </>
        )}
        {tab === 'day' && <DailyLife onWrite={() => setTab('ai')} />}
        {tab === 'trends' && <Trends />}
        {tab === 'community' && <Community />}
        {tab === 'counsellors' && <Counsellors />}
        {tab === 'friends' && <Friends />}
      </main>
    </div>
  )
}
