import { ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { addFriend, deleteFriend, listFriends } from '../api'
import type { Friend } from '../api'

export default function Friends() {
  const [friends, setFriends] = useState<Friend[]>([])
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    try {
      setFriends(await listFriends())
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
    </div>
  )
}
