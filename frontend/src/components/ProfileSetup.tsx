import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Check, MailCheck, Plus, X } from 'lucide-react'
import { getLanguages, startAddEmail, updateProfile, verifyAddEmail } from '../api'
import type { Language, User } from '../api'

interface ProfileSetupProps {
  user: User
  /** First-time setup (shows the welcome copy and a "later" option) or editing. */
  onboarding: boolean
  onSaved: (user: User) => void
  onClose: () => void
}

const SUGGESTED_INTERESTS = [
  'Studies',
  'Exams',
  'Placements',
  'Sleep',
  'Friendships',
  'Family',
  'Relationships',
  'Fitness',
  'Music',
  'Movies',
  'Gaming',
  'Coding',
  'Art',
  'Reading',
  'Sports',
  'Travel',
  'Food',
  'Spirituality',
]

/** Name, language, interests, and (for older accounts) a verified email. */
export default function ProfileSetup({ user, onboarding, onSaved, onClose }: ProfileSetupProps) {
  const [languages, setLanguages] = useState<Language[]>([])
  const [name, setName] = useState(user.preferred_name ?? '')
  const [language, setLanguage] = useState(user.language ?? '')
  const [interests, setInterests] = useState<string[]>(user.interests ?? [])
  const [custom, setCustom] = useState('')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [codeSent, setCodeSent] = useState(false)
  const [devDelivery, setDevDelivery] = useState(false)
  const [current, setCurrent] = useState(user)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getLanguages()
      .then(setLanguages)
      .catch(() => setLanguages([{ code: 'en', label: 'English' }]))
  }, [])

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

  function toggleInterest(item: string) {
    setInterests((prev) =>
      prev.some((p) => p.toLowerCase() === item.toLowerCase())
        ? prev.filter((p) => p.toLowerCase() !== item.toLowerCase())
        : [...prev, item].slice(0, 12),
    )
  }

  function addCustom(e: FormEvent) {
    e.preventDefault()
    const item = custom.trim()
    if (item) toggleInterest(item)
    setCustom('')
  }

  function sendCode() {
    run(async () => {
      const res = await startAddEmail(email.trim())
      setDevDelivery(res.delivery === 'log')
      setCodeSent(true)
    })
  }

  function confirmCode() {
    run(async () => {
      const updated = await verifyAddEmail(email.trim(), code.trim())
      setCurrent(updated)
      setCodeSent(false)
    })
  }

  function save(e: FormEvent) {
    e.preventDefault()
    if (!language) {
      setError('Pick the language you usually speak.')
      return
    }
    run(async () => {
      const updated = await updateProfile({ preferred_name: name.trim() || null, language, interests })
      onSaved(updated)
    })
  }

  const extraInterests = interests.filter(
    (i) => !SUGGESTED_INTERESTS.some((s) => s.toLowerCase() === i.toLowerCase()),
  )

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="profile-title">
      <div className="glass modal profile-setup">
        <button type="button" className="icon-btn modal-close" onClick={onClose} aria-label="Close">
          <X size={18} />
        </button>
        <h2 id="profile-title">{onboarding ? 'Finish setting up your account' : 'Your profile'}</h2>
        {onboarding && (
          <p className="muted">
            A few quick things so HealAura talks to you the way you like. You can change these any time.
          </p>
        )}

        <form onSubmit={save} className="stack">
          <label className="field">
            <span>What should HealAura call you?</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={user.username}
              maxLength={40}
            />
          </label>

          <fieldset className="field">
            <legend>Which language do you usually speak?</legend>
            <div className="chip-grid">
              {languages.map((l) => (
                <button
                  key={l.code}
                  type="button"
                  className={`chip${language === l.code ? ' active' : ''}`}
                  aria-pressed={language === l.code}
                  onClick={() => setLanguage(l.code)}
                >
                  {language === l.code && <Check size={13} aria-hidden="true" />}
                  {l.label}
                </button>
              ))}
            </div>
            <span className="muted small">
              HealAura always replies in the language you write in; this is the fallback.
            </span>
          </fieldset>

          <fieldset className="field">
            <legend>What are you into? (optional)</legend>
            <div className="chip-grid">
              {[...SUGGESTED_INTERESTS, ...extraInterests].map((item) => {
                const on = interests.some((i) => i.toLowerCase() === item.toLowerCase())
                return (
                  <button
                    key={item}
                    type="button"
                    className={`chip${on ? ' active' : ''}`}
                    aria-pressed={on}
                    onClick={() => toggleInterest(item)}
                  >
                    {item}
                  </button>
                )
              })}
            </div>
          </fieldset>
        </form>
        <form onSubmit={addCustom} className="inline-add">
          <input
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            placeholder="Add your own…"
            maxLength={30}
            aria-label="Add an interest"
          />
          <button type="submit" className="icon-btn" aria-label="Add interest" disabled={!custom.trim()}>
            <Plus size={16} />
          </button>
        </form>

        <div className="field email-block">
          <span className="field-label">Email</span>
          {current.email ? (
            <p className="ok small">
              <MailCheck size={15} aria-hidden="true" className="inline-icon" /> {current.email} (verified)
            </p>
          ) : (
            <>
              <p className="muted small">
                Add an email so HealAura can reach you (and your close friends' check-ins can tell
                you they went out).
              </p>
              {!codeSent ? (
                <div className="inline-add">
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    aria-label="Email to add"
                  />
                  <button type="button" className="ghost" onClick={sendCode} disabled={busy || !email.trim()}>
                    Send code
                  </button>
                </div>
              ) : (
                <>
                  {devDelivery && (
                    <p className="notice">Email isn't set up on the server, so the code went to the backend log.</p>
                  )}
                  <div className="inline-add">
                    <input
                      className="code-input small-code"
                      value={code}
                      onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      placeholder="6-digit code"
                      aria-label="Verification code"
                    />
                    <button type="button" className="ghost" onClick={confirmCode} disabled={busy || code.length !== 6}>
                      Verify
                    </button>
                  </div>
                </>
              )}
            </>
          )}
        </div>

        {error && <p className="error">{error}</p>}
        <div className="modal-actions">
          {onboarding && (
            <button type="button" className="link" onClick={onClose}>
              Remind me later
            </button>
          )}
          <button type="button" className="primary" onClick={save} disabled={busy || !language}>
            {busy ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
