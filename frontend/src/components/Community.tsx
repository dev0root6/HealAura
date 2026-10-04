import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { CornerDownRight, Hash, Plus, Send, Sparkles, X } from 'lucide-react'
import { createChannel, getChannelMessages, getChannels, postChannelMessage } from '../api'
import type { Channel, CommunityMessage } from '../api'
import { useCommunitySocket } from '../hooks/useCommunitySocket'

const LAST_CHANNEL_KEY = 'healaura:last-channel'
const TYPING_SHOWN_MS = 3500

function readLastChannel(): string | null {
  try {
    return localStorage.getItem(LAST_CHANNEL_KEY)
  } catch {
    return null
  }
}

function timeLabel(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

export default function Community() {
  const [channels, setChannels] = useState<Channel[]>([])
  const [active, setActive] = useState<string | null>(null)
  const [messages, setMessages] = useState<CommunityMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [unread, setUnread] = useState<Record<string, number>>({})
  const [typing, setTyping] = useState<Record<string, number>>({}) // handle -> shown until
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const endRef = useRef<HTMLDivElement>(null)
  const activeRef = useRef<string | null>(null)
  activeRef.current = active

  // --- live events ---
  const addMessage = useCallback((m: CommunityMessage) => {
    if (m.channel_id === activeRef.current) {
      setMessages((prev) => (prev.some((p) => p.id === m.id) ? prev : [...prev, m]))
      setTyping((t) => {
        const { [m.handle]: _gone, ...rest } = t
        return rest
      })
    } else if (m.channel_id) {
      setUnread((u) => ({ ...u, [m.channel_id as string]: (u[m.channel_id as string] ?? 0) + 1 }))
    }
  }, [])

  const live = useCommunitySocket(active, {
    onMessage: addMessage,
    onChannel: (c) => setChannels((prev) => (prev.some((p) => p.id === c.id) ? prev : [...prev, c])),
    onTyping: (handle, channelId) => {
      if (channelId === activeRef.current) setTyping((t) => ({ ...t, [handle]: Date.now() + TYPING_SHOWN_MS }))
    },
  })

  // Expire typing hints.
  useEffect(() => {
    if (!Object.keys(typing).length) return
    const id = setInterval(() => {
      const now = Date.now()
      setTyping((t) => Object.fromEntries(Object.entries(t).filter(([, until]) => until > now)))
    }, 1000)
    return () => clearInterval(id)
  }, [typing])

  // --- loading ---
  useEffect(() => {
    getChannels()
      .then((list) => {
        setChannels(list)
        const remembered = readLastChannel()
        const start =
          list.find((c) => c.id === remembered) ?? list.find((c) => c.slug === 'general') ?? list[0]
        setActive(start?.id ?? null)
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
  }, [])

  const loadMessages = useCallback(async (channelId: string) => {
    try {
      const list = await getChannelMessages(channelId)
      if (activeRef.current === channelId) setMessages(list)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!active) return
    setLoading(true)
    setMessages([])
    setTyping({})
    setUnread((u) => ({ ...u, [active]: 0 }))
    try {
      localStorage.setItem(LAST_CHANNEL_KEY, active)
    } catch {
      /* not remembered next time */
    }
    loadMessages(active)
  }, [active, loadMessages])

  // If the live socket is down, fall back to polling the open channel.
  useEffect(() => {
    if (!active || live.status === 'live') return
    const id = setInterval(() => loadMessages(active), 10000)
    return () => clearInterval(id)
  }, [active, live.status, loadMessages])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages, typing])

  // --- actions ---
  async function send(e?: FormEvent) {
    e?.preventDefault()
    const content = text.trim()
    if (!content || busy || !active) return
    setBusy(true)
    setError(null)
    try {
      addMessage(await postChannelMessage(active, content))
      setText('')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  function onComposerKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  async function submitChannel(e: FormEvent) {
    e.preventDefault()
    if (busy || !newName.trim()) return
    setBusy(true)
    setError(null)
    try {
      const c = await createChannel(newName.trim(), newDesc.trim())
      setChannels((prev) => (prev.some((p) => p.id === c.id) ? prev : [...prev, c]))
      setActive(c.id)
      setCreating(false)
      setNewName('')
      setNewDesc('')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const channel = channels.find((c) => c.id === active)
  const byId = useMemo(() => new Map(messages.map((m) => [m.id, m])), [messages])
  const typingNames = Object.keys(typing).filter((h) => h !== live.handle)
  const hereNow = active ? (live.perChannel[active] ?? 0) : 0

  return (
    <div className="glass community-shell">
      <aside className="channel-list" aria-label="Channels">
        <div className="channel-list-head">
          <span>Channels</span>
          <button
            type="button"
            className="icon-btn"
            onClick={() => setCreating((v) => !v)}
            aria-label={creating ? 'Cancel new channel' : 'Create a channel'}
            title="Create a channel"
          >
            {creating ? <X size={16} /> : <Plus size={16} />}
          </button>
        </div>

        {creating && (
          <form className="new-channel" onSubmit={submitChannel}>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="channel-name"
              maxLength={40}
              aria-label="Channel name"
              autoFocus
            />
            <input
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="What's it for? (optional)"
              maxLength={140}
              aria-label="Channel description"
            />
            <button type="submit" className="primary" disabled={busy || !newName.trim()}>
              Create
            </button>
          </form>
        )}

        <ul>
          {channels.map((c) => {
            const count = unread[c.id] ?? 0
            const here = live.perChannel[c.id] ?? 0
            return (
              <li key={c.id}>
                <button
                  type="button"
                  className={`channel-item${c.id === active ? ' active' : ''}${count ? ' unread' : ''}`}
                  onClick={() => setActive(c.id)}
                  aria-current={c.id === active ? 'true' : undefined}
                >
                  <Hash size={15} aria-hidden="true" />
                  <span className="channel-name">{c.name}</span>
                  {here > 0 && (
                    <span className="here-dot" title={`${here} here now`}>
                      {here}
                    </span>
                  )}
                  {count > 0 && <span className="unread-badge">{count > 99 ? '99+' : count}</span>}
                </button>
              </li>
            )
          })}
        </ul>
        <p className="channel-foot muted small">
          <span className={`live-dot ${live.status}`} aria-hidden="true" />
          {live.status === 'live'
            ? `${live.online} online`
            : live.status === 'connecting'
              ? 'Connecting…'
              : 'Offline · retrying'}
          {live.handle && (
            <>
              {' · '}you're <strong>{live.handle}</strong>
            </>
          )}
        </p>
      </aside>

      <section className="channel-pane" aria-label={channel ? `#${channel.name}` : 'Channel'}>
        <header className="channel-header">
          <h2>
            <Hash size={18} aria-hidden="true" />
            {channel?.name ?? '…'}
          </h2>
          {channel?.description && <p className="muted small">{channel.description}</p>}
          {hereNow > 0 && <span className="here-now">{hereNow} here now</span>}
        </header>

        <div className="community-feed" aria-live="polite">
          {loading && <p className="muted">Loading…</p>}
          {!loading && messages.length === 0 && (
            <p className="muted">No messages in #{channel?.name} yet. Say something kind.</p>
          )}
          {messages.map((m) => {
            const parent = m.reply_to ? byId.get(m.reply_to) : undefined
            const mine = !m.is_bot && m.handle === live.handle
            return (
              <div key={m.id} className={`community-msg${m.is_bot ? ' bot' : ''}${mine ? ' mine' : ''}`}>
                <span className="community-handle">
                  {mine ? 'You' : m.handle}
                  {m.is_bot && (
                    <span className="ai-badge" title="AI companion">
                      <Sparkles size={11} aria-hidden="true" /> AI
                    </span>
                  )}
                  <time className="msg-time" dateTime={m.created_at}>
                    {timeLabel(m.created_at)}
                  </time>
                </span>
                {parent && (
                  <span className="community-reply-to">
                    <CornerDownRight size={12} aria-hidden="true" /> replying to{' '}
                    {parent.handle === live.handle ? 'you' : parent.handle}
                  </span>
                )}
                <p className="community-text">{m.content}</p>
              </div>
            )
          })}
          {typingNames.length > 0 && (
            <p className="typing-line muted small">
              <span className="typing-dots" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
              {typingNames.slice(0, 2).join(' and ')}
              {typingNames.length > 2 ? ' and others' : ''} {typingNames.length === 1 ? 'is' : 'are'}{' '}
              typing…
            </p>
          )}
          <div ref={endRef} />
        </div>

        {error && <p className="error">{error}</p>}
        <form onSubmit={send} className="community-compose">
          <textarea
            value={text}
            onChange={(e) => {
              setText(e.target.value)
              if (e.target.value) live.sendTyping()
            }}
            onKeyDown={onComposerKey}
            placeholder={channel ? `Message #${channel.name}` : 'Say something…'}
            maxLength={1000}
            rows={1}
            disabled={busy || !active}
          />
          <button type="submit" className="primary" disabled={busy || !text.trim()} aria-label="Send">
            <Send size={16} aria-hidden="true" />
          </button>
        </form>
        <p className="muted small compose-hint">
          Anonymous: your handle changes daily. Messages marked <span className="ai-badge">AI</span> are
          from HealAura's companions.
        </p>
      </section>
    </div>
  )
}
