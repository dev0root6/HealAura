import { useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowLeft } from 'lucide-react'
import { login } from '../api'
import type { User } from '../api'
import Logo from './Logo'

interface LoginProps {
  onLoggedIn: (user: User) => void
  onBack: () => void
  onSignUp: () => void
}

export default function Login({ onLoggedIn, onBack, onSignUp }: LoginProps) {
  const [identity, setIdentity] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (busy || !identity.trim() || !password) return
    setBusy(true)
    setError(null)
    try {
      const { user } = await login(identity.trim(), password)
      onLoggedIn(user)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-screen">
      <div className="glow" aria-hidden="true" />
      <div className="glass auth-card">
        <button type="button" className="link back" onClick={onBack}>
          <ArrowLeft size={15} aria-hidden="true" /> Back
        </button>
        <h1 className="brand-lockup">
          <Logo size={44} />
          <span className="brand">HealAura</span>
        </h1>
        <p className="muted center">Welcome back. Sign in to continue.</p>
        <form onSubmit={handleSubmit} className="stack">
          <label className="field">
            <span>Email or username</span>
            <input
              value={identity}
              onChange={(e) => setIdentity(e.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <button type="submit" className="primary" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        {error && <p className="error">{error}</p>}
        <p className="muted small center hint">
          New here?{' '}
          <button type="button" className="link" onClick={onSignUp}>
            Create an account
          </button>
        </p>
      </div>
    </div>
  )
}
