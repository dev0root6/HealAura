import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowLeft, KeyRound, MailCheck } from 'lucide-react'
import { completeRegistration, startRegistration, verifyRegistration } from '../api'
import type { User } from '../api'
import Logo from './Logo'

interface SignupProps {
  onSignedUp: (user: User) => void
  onBack: () => void
  onSignIn: () => void
}

type Step = 'email' | 'code' | 'account'

const RESEND_SECONDS = 60

/** Three steps: email -> 6-digit code from HealAura's email -> username & password. */
export default function Signup({ onSignedUp, onBack, onSignIn }: SignupProps) {
  const [step, setStep] = useState<Step>('email')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [signupToken, setSignupToken] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [devDelivery, setDevDelivery] = useState(false)
  const [resendIn, setResendIn] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (resendIn <= 0) return
    const id = setTimeout(() => setResendIn((s) => s - 1), 1000)
    return () => clearTimeout(id)
  }, [resendIn])

  async function run(action: () => Promise<void>) {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  function sendCode(e?: FormEvent) {
    e?.preventDefault()
    run(async () => {
      const res = await startRegistration(email.trim())
      setDevDelivery(res.delivery === 'log')
      setCode('')
      setResendIn(RESEND_SECONDS)
      setStep('code')
    })
  }

  function checkCode(e: FormEvent) {
    e.preventDefault()
    run(async () => {
      const res = await verifyRegistration(email.trim(), code.trim())
      setSignupToken(res.signup_token)
      setStep('account')
    })
  }

  function createAccount(e: FormEvent) {
    e.preventDefault()
    if (password !== confirm) {
      setError("Passwords don't match.")
      return
    }
    run(async () => {
      const { user } = await completeRegistration(signupToken, username.trim(), password)
      onSignedUp(user)
    })
  }

  return (
    <div className="auth-screen">
      <div className="glow" aria-hidden="true" />
      <div className="glass auth-card">
        <button
          type="button"
          className="link back"
          onClick={step === 'code' ? () => setStep('email') : onBack}
        >
          <ArrowLeft size={15} aria-hidden="true" /> Back
        </button>
        <h1 className="brand-lockup">
          <Logo size={44} />
          <span className="brand">HealAura</span>
        </h1>
        <ol className="steps" aria-label="Sign-up progress">
          {(['email', 'code', 'account'] as Step[]).map((s, i) => (
            <li key={s} className={s === step ? 'current' : undefined}>
              {i + 1}. {s === 'email' ? 'Email' : s === 'code' ? 'Verify' : 'Account'}
            </li>
          ))}
        </ol>

        {step === 'email' && (
          <form onSubmit={sendCode} className="stack">
            <p className="muted center">
              We'll email you a 6-digit code to make sure this address is yours.
            </p>
            <label className="field">
              <span>Email</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
              />
            </label>
            <button type="submit" className="primary" disabled={busy || !email.trim()}>
              {busy ? 'Sending…' : 'Send code'}
            </button>
          </form>
        )}

        {step === 'code' && (
          <form onSubmit={checkCode} className="stack">
            <p className="muted center">
              <MailCheck size={16} aria-hidden="true" className="inline-icon" /> We sent a code to{' '}
              <strong>{email}</strong>. It expires in 10 minutes.
            </p>
            {devDelivery && (
              <p className="notice">
                Email isn't set up on this server yet, so the code was written to the backend log.
              </p>
            )}
            <label className="field">
              <span>Verification code</span>
              <input
                className="code-input"
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="000000"
                required
              />
            </label>
            <button type="submit" className="primary" disabled={busy || code.length !== 6}>
              {busy ? 'Checking…' : 'Verify'}
            </button>
            <button
              type="button"
              className="link center"
              disabled={busy || resendIn > 0}
              onClick={() => sendCode()}
            >
              {resendIn > 0 ? `Resend code in ${resendIn}s` : 'Resend code'}
            </button>
          </form>
        )}

        {step === 'account' && (
          <form onSubmit={createAccount} className="stack">
            <p className="muted center">
              <KeyRound size={16} aria-hidden="true" className="inline-icon" /> Email verified. Pick a
              username and password.
            </p>
            <label className="field">
              <span>Username</span>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                pattern="[A-Za-z0-9_.\-]{3,32}"
                title="3–32 letters, numbers, dots, dashes or underscores"
                required
              />
            </label>
            <label className="field">
              <span>Password</span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                minLength={8}
                required
              />
            </label>
            <label className="field">
              <span>Confirm password</span>
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
                minLength={8}
                required
              />
            </label>
            <button type="submit" className="primary" disabled={busy}>
              {busy ? 'Creating account…' : 'Create account'}
            </button>
          </form>
        )}

        {error && <p className="error">{error}</p>}
        {step === 'email' && (
          <p className="muted small center hint">
            Already have an account?{' '}
            <button type="button" className="link" onClick={onSignIn}>
              Sign in
            </button>
          </p>
        )}
      </div>
    </div>
  )
}
