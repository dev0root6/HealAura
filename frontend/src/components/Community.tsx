import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ChangeEvent, FormEvent, KeyboardEvent, ReactNode } from 'react'
import {
  AtSign,
  Check,
  Clock3,
  CornerDownRight,
  Hash,
  ImagePlus,
  Pencil,
  Plus,
  Send,
  Sparkles,
  X,
} from 'lucide-react'
import {
  checkAlias,
  communityImageUrl,
  createChannel,
  getChannelMessages,
  getChannels,
  postChannelMessage,
  searchMembers,
  setAlias,
  uploadCommunityImage,
} from '../api'
import type { Channel, CommunityMessage, Member } from '../api'
import { useCommunitySocket } from '../hooks/useCommunitySocket'

const LAST_CHANNEL_KEY = 'healaura:last-channel'
const TYPING_SHOWN_MS = 3500
const AI_ALIAS = 'HealAura'
const MENTION_SPLIT = /(@[A-Za-z][A-Za-z0-9_]{2,19})/g
const MENTION_AT_CARET = /(?:^|\s)@([A-Za-z0-9_]{0,20})$/

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

function mentionsAlias(text: string, alias: string | null | undefined): boolean {
  if (!alias || !text) return false
  return new RegExp(`(^|[^A-Za-z0-9_])@${alias}\\b`, 'i').test(text)
}

/** Message text with @mentions highlighted (and "you" when it's this person). */
function renderText(text: string, me: string | null | undefined): ReactNode[] {
  return text.split(MENTION_SPLIT).map((part, i) => {
    if (i % 2 === 0) return part
    const name = part.slice(1)
    const self = !!me && name.toLowerCase() === me.toLowerCase()
    const ai = name.toLowerCase() === AI_ALIAS.toLowerCase()
    return (
      <span key={i} className={`mention${self ? ' me' : ''}${ai ? ' ai' : ''}`}>
        {part}
      </span>
    )
  })
}

/** Pick (and check) a public community alias. */
function AliasSetup({
  current,
  onSaved,
  onCancel,
}: {
  current: string | null
  onSaved: (alias: string) => void
  onCancel?: () => void
}) {
  const [name, setName] = useState(current ?? '')
  const [check, setCheck] = useState<{ available: boolean; reason: string | null } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const value = name.trim()
    if (!value || value === current) {
      setCheck(null)
      return
    }
    const id = setTimeout(() => {
      checkAlias(value)
        .then(setCheck)
        .catch(() => setCheck(null))
    }, 300)
    return () => clearTimeout(id)
  }, [name, current])

  async function save(e: FormEvent) {
    e.preventDefault()
    if (busy || !name.trim()) return
    setBusy(true)
    setError(null)
    try {
      onSaved(await setAlias(name.trim()))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="alias-setup" onSubmit={save}>
      <h3>{current ? 'Change your community alias' : 'Choose your community alias'}</h3>
      <p className="muted small">
        This is the name people see and can @mention. It isn't your login and it stays the same
        until you change it.
      </p>
      <div className="inline-add">
        <span className="alias-at" aria-hidden="true">
          @
        </span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value.replace(/[^A-Za-z0-9_]/g, '').slice(0, 20))}
          placeholder="your_alias"
          aria-label="Community alias"
          autoFocus
        />
        <button type="submit" className="primary" disabled={busy || !name.trim() || check?.available === false}>
          {busy ? 'Saving…' : 'Save'}
        </button>
        {onCancel && (
          <button type="button" className="icon-btn" onClick={onCancel} aria-label="Cancel">
            <X size={16} />
          </button>
        )}
      </div>
      {check && (
        <p className={`small ${check.available ? 'ok' : 'error'}`}>
          {check.available ? (
            <>
              <Check size={13} aria-hidden="true" className="inline-icon" /> @{name.trim()} is available
            </>
          ) : (
            check.reason
          )}
        </p>
      )}
      {error && <p className="error small">{error}</p>}
    </form>
  )
}

export default function Community() {
  const [channels, setChannels] = useState<Channel[]>([])
  const [active, setActive] = useState<string | null>(null)
  const [messages, setMessages] = useState<CommunityMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [unread, setUnread] = useState<Record<string, number>>({})
  const [mentioned, setMentioned] = useState<Record<string, boolean>>({})
  const [toast, setToast] = useState<{ channelId: string; text: string } | null>(null)
  const [typing, setTyping] = useState<Record<string, number>>({}) // handle -> shown until
  const [text, setText] = useState('')
  const [image, setImage] = useState<{ file: File; preview: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [editingAlias, setEditingAlias] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [suggest, setSuggest] = useState<{ query: string; items: Member[]; index: number } | null>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
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
    onMention: ({ channelId, channelName, from }) => {
      if (channelId !== activeRef.current) {
        setMentioned((m) => ({ ...m, [channelId]: true }))
        setToast({ channelId, text: `@${from} mentioned you in #${channelName}` })
      }
    },
  })
  const me = live.handle

  useEffect(() => {
    if (!toast) return
    const id = setTimeout(() => setToast(null), 6000)
    return () => clearTimeout(id)
  }, [toast])

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
    setMentioned((m) => ({ ...m, [active]: false }))
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

  // --- @mention autocomplete ---
  useEffect(() => {
    if (!suggest) return
    let cancelled = false
    const id = setTimeout(() => {
      searchMembers(suggest.query)
        .then((items) => !cancelled && setSuggest((s) => (s ? { ...s, items, index: 0 } : s)))
        .catch(() => {})
    }, 150)
    return () => {
      cancelled = true
      clearTimeout(id)
    }
    // Only refetch when the query text changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [suggest?.query])

  function onTextChange(e: ChangeEvent<HTMLTextAreaElement>) {
    const value = e.target.value
    setText(value)
    if (value) live.sendTyping()
    const before = value.slice(0, e.target.selectionStart ?? value.length)
    const match = before.match(MENTION_AT_CARET)
    setSuggest(match ? (s) => (s && s.query === match[1] ? s : { query: match[1], items: s?.items ?? [], index: 0 }) : null)
  }

  function pickMention(alias: string) {
    const el = inputRef.current
    const caret = el?.selectionStart ?? text.length
    const before = text.slice(0, caret).replace(/@([A-Za-z0-9_]{0,20})$/, `@${alias} `)
    const next = before + text.slice(caret)
    setText(next)
    setSuggest(null)
    requestAnimationFrame(() => {
      el?.focus()
      el?.setSelectionRange(before.length, before.length)
    })
  }

  // --- actions ---
  async function send(e?: FormEvent) {
    e?.preventDefault()
    const content = text.trim()
    if ((!content && !image) || busy || !active) return
    setBusy(true)
    setError(null)
    try {
      const imageId = image ? (await uploadCommunityImage(image.file)).id : null
      addMessage(await postChannelMessage(active, content, imageId))
      setText('')
      clearImage()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  function onComposerKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (suggest && suggest.items.length) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        const step = e.key === 'ArrowDown' ? 1 : -1
        setSuggest({ ...suggest, index: (suggest.index + step + suggest.items.length) % suggest.items.length })
        return
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault()
        pickMention(suggest.items[suggest.index].alias)
        return
      }
      if (e.key === 'Escape') {
        setSuggest(null)
        return
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  function onPickImage(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setError('Only images can be shared.')
      return
    }
    if (file.size > 8 * 1024 * 1024) {
      setError('Images can be up to 8 MB.')
      return
    }
    clearImage()
    setImage({ file, preview: URL.createObjectURL(file) })
  }

  function clearImage() {
    setImage((img) => {
      if (img) URL.revokeObjectURL(img.preview)
      return null
    })
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
  const typingNames = Object.keys(typing).filter((h) => h !== me)
  const hereNow = active ? (live.perChannel[active] ?? 0) : 0
  const needsAlias = me === null

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
                  {mentioned[c.id] && (
                    <span className="mention-badge" title="You were mentioned">
                      <AtSign size={11} aria-hidden="true" />
                    </span>
                  )}
                  {count > 0 && <span className="unread-badge">{count > 99 ? '99+' : count}</span>}
                </button>
              </li>
            )
          })}
        </ul>
        <div className="channel-foot muted small">
          <span className={`live-dot ${live.status}`} aria-hidden="true" />
          {live.status === 'live'
            ? `${live.online} online`
            : live.status === 'connecting'
              ? 'Connecting…'
              : 'Offline · retrying'}
          {me && (
            <>
              {' · '}
              <strong>@{me}</strong>
              <button
                type="button"
                className="icon-btn tiny"
                onClick={() => setEditingAlias(true)}
                aria-label="Change your alias"
                title="Change your alias"
              >
                <Pencil size={12} />
              </button>
            </>
          )}
        </div>
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

        {toast && (
          <button type="button" className="mention-toast" onClick={() => setActive(toast.channelId)}>
            <AtSign size={14} aria-hidden="true" /> {toast.text}
          </button>
        )}

        <div className="community-feed" aria-live="polite">
          {loading && <p className="muted">Loading…</p>}
          {!loading && messages.length === 0 && (
            <p className="muted">No messages in #{channel?.name} in the last 24 hours. Say something kind.</p>
          )}
          {messages.map((m) => {
            const parent = m.reply_to ? byId.get(m.reply_to) : undefined
            const mine = !m.is_bot && !!me && m.handle === me
            const forMe = !mine && mentionsAlias(m.content, me)
            return (
              <div
                key={m.id}
                className={`community-msg${m.is_bot ? ' bot' : ''}${mine ? ' mine' : ''}${forMe ? ' for-me' : ''}`}
              >
                <span className="community-handle">
                  {mine ? 'You' : m.handle}
                  {m.is_bot && (
                    <span className="ai-badge" title="AI">
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
                    {parent.handle === me ? 'you' : `@${parent.handle}`}
                  </span>
                )}
                {m.image_id && (
                  <a href={communityImageUrl(m.image_id)} target="_blank" rel="noreferrer" className="msg-image">
                    <img src={communityImageUrl(m.image_id)} alt="Shared image" loading="lazy" />
                  </a>
                )}
                {m.content && <p className="community-text">{renderText(m.content, me)}</p>}
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

        {error && <p className="error compose-error">{error}</p>}

        {needsAlias || editingAlias ? (
          <AliasSetup
            current={me ?? null}
            onSaved={(alias) => {
              live.setHandle(alias)
              setEditingAlias(false)
            }}
            onCancel={editingAlias ? () => setEditingAlias(false) : undefined}
          />
        ) : (
          <>
            {image && (
              <div className="attach-preview">
                <img src={image.preview} alt="Image to send" />
                <button type="button" className="icon-btn" onClick={clearImage} aria-label="Remove image">
                  <X size={16} />
                </button>
              </div>
            )}
            <form onSubmit={send} className="community-compose">
              {suggest && suggest.items.length > 0 && (
                <ul className="mention-menu" role="listbox" aria-label="Mention someone">
                  {suggest.items.map((item, i) => (
                    <li key={item.alias} role="option" aria-selected={i === suggest.index}>
                      <button
                        type="button"
                        className={i === suggest.index ? 'active' : undefined}
                        onMouseDown={(e) => {
                          e.preventDefault()
                          pickMention(item.alias)
                        }}
                      >
                        <AtSign size={13} aria-hidden="true" />
                        {item.alias}
                        {item.is_ai && <span className="ai-badge">AI</span>}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <input ref={fileRef} type="file" accept="image/*" hidden onChange={onPickImage} />
              <button
                type="button"
                className="icon-btn attach"
                onClick={() => fileRef.current?.click()}
                aria-label="Attach an image"
                title="Attach an image (deleted after 24 hours)"
                disabled={busy || !active}
              >
                <ImagePlus size={18} />
              </button>
              <textarea
                ref={inputRef}
                value={text}
                onChange={onTextChange}
                onKeyDown={onComposerKey}
                onBlur={() => setTimeout(() => setSuggest(null), 150)}
                placeholder={channel ? `Message #${channel.name} · @ to mention, @HealAura to ask the AI` : 'Say something…'}
                maxLength={1000}
                rows={1}
                disabled={busy || !active}
              />
              <button
                type="submit"
                className="primary"
                disabled={busy || (!text.trim() && !image)}
                aria-label="Send"
              >
                <Send size={16} aria-hidden="true" />
              </button>
            </form>
          </>
        )}
        <p className="muted small compose-hint">
          <Clock3 size={12} aria-hidden="true" className="inline-icon" /> Messages and images disappear after 24
          hours. <span className="ai-badge">AI</span> marks HealAura's replies.
        </p>
      </section>
    </div>
  )
}
