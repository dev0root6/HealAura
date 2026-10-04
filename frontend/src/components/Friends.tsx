import { MailCheck, Send, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { addFriend, deleteFriend, getAlertStatus, listFriends, sendTestAlert } from '../api'
import type { AlertStatus, Friend } from '../api'

const REASON_LABEL: Record<string, string> = {
  crisis: 'Urgent check-in',
  sustained: 'Check-in',
  test: 'Test email',
}

function when(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export default function Friends() {
  const [friends, setFriends] = useState<Friend[]>([])
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<AlertStatus | null>(null)
  const [testMsg, setTestMsg] = useState<string | null>(null)

  async function load() {
    try {
      const [list, alerts] = await Promise.all([listFriends(), getAlertStatus()])
      setFriends(list)
      setStatus(alerts)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  useEffect(() => {
    load()
  }, [])

  async function handleAdd(e: FormEvent) {
    e.preventDefault()
    if (busy || !name.trim() || !email.trim()) return
    setBusy(true)
    setError(null)
    try {
      await addFriend(name.trim(), email.trim())
      setName('')
      setEmail('')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function handleRemove(id: string) {
    try {
      await deleteFriend(id)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleTest() {
    if (busy) return
    setBusy(true)
    setTestMsg(null)
    setError(null)
    try {
      await sendTestAlert()
      setTestMsg('Test sent. Ask your friends to check their inbox (and spam).')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const cooling =
    status?.next_allowed_at && new Date(status.next_allowed_at).getTime() > Date.now()
      ? status.next_allowed_at
      : null

  return (
    <div className="stack">
      <div className="glass panel">
        <h2>Your close friends</h2>
        <p className="muted">
          Add people you trust. HealAura's well-being agent quietly watches your
          reflections — and <strong>only</strong> if it senses you're going through a
          sustained rough patch will it gently let these friends know you could use
          support. It never shares what you wrote.
        </p>
        <div className="agent-note">
          <ShieldCheck size={18} aria-hidden="true" />
          <span>Automatic · opt-in · privacy-first — you're always in control of this list.</span>
        </div>
        <form onSubmit={handleAdd} className="stack">
          <label className="field">
            <span>Friend's name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Alex" required />
          </label>
          <label className="field">
            <span>Friend's email</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="alex@example.com"
              required
            />
          </label>
          <button type="submit" className="primary" disabled={busy}>
            {busy ? 'Adding…' : 'Add friend'}
          </button>
        </form>
        {error && <p className="error">{error}</p>}
      </div>

      <div className="glass panel">
        <h2>Trusted circle</h2>
        {friends.length === 0 && (
          <p className="muted">No one yet. Add someone you'd want checking in on you.</p>
        )}
        <ul className="friend-list">
          {friends.map((f) => (
            <li key={f.id} className="friend-row">
              <span className="avatar" aria-hidden="true">
                {f.name.slice(0, 1).toUpperCase()}
              </span>
              <div className="friend-info">
                <span className="user-name">{f.name}</span>
                <span className="muted small">{f.email}</span>
              </div>
              <button type="button" className="danger-btn" onClick={() => handleRemove(f.id)}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="glass panel">
        <h2>Check-in emails</h2>
        {status && !status.email_configured && (
          <p className="notice">Email isn't set up on the server yet, so no check-ins can be sent.</p>
        )}
        <p className="muted small">
          HealAura emails your friends (and you, with helplines) when it senses a sustained rough
          patch, waiting {status?.cooldown_hours ?? 12} hours before sending another of those.
          {cooling && <> Next one possible after {when(cooling)}.</>} If you ever mention self-harm or
          suicide, it emails them straight away, every time (at most once an hour).
        </p>
        <div className="test-row">
          <button
            type="button"
            className="ghost"
            onClick={handleTest}
            disabled={busy || friends.length === 0}
          >
            <Send size={15} aria-hidden="true" /> Send a test email to my friends
          </button>
          {testMsg && (
            <span className="ok small">
              <MailCheck size={15} aria-hidden="true" className="inline-icon" /> {testMsg}
            </span>
          )}
        </div>
        {status && status.alerts.length > 0 ? (
          <ul className="alert-list">
            {status.alerts.map((a) => (
              <li key={a.created_at}>
                <strong>{REASON_LABEL[a.reason] ?? a.reason}</strong>
                <span className="muted small">{when(a.created_at)}</span>
                <span className="small">
                  {a.friends_sent} friend{a.friends_sent === 1 ? '' : 's'} emailed
                  {a.friends_failed > 0 && <span className="error"> · {a.friends_failed} failed</span>}
                  {a.self_sent && ' · you too'}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted small">No check-ins sent yet.</p>
        )}
      </div>
    </div>
  )
}
