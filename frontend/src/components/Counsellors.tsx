import { useEffect, useState } from 'react'
import { Mail, Phone } from 'lucide-react'
import { getCounsellors } from '../api'
import type { Counsellor } from '../api'

export default function Counsellors() {
  const [list, setList] = useState<Counsellor[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getCounsellors()
      .then(setList)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="stack">
      <div className="glass panel">
        <h2>Talk with a counsellor</h2>
        <p className="muted">
          Trained professionals you can reach out to directly. Demo directory.
        </p>
      </div>
      {loading && <p className="muted">Loading…</p>}
      {error && <p className="error">{error}</p>}
      <ul className="card-grid">
        {list.map((c) => (
          <li key={c.email} className="glass counsellor-card">
            <div className="counsellor-head">
              <span className="avatar" aria-hidden="true">
                {c.name.split(' ').map((w) => w[0]).slice(0, 2).join('')}
              </span>
              <div>
                <p className="counsellor-name">{c.name}</p>
                <p className="counsellor-title">{c.title}</p>
              </div>
            </div>
            <p className="counsellor-langs">{c.languages.join(' · ')}</p>
            <p className="counsellor-avail muted">{c.available}</p>
            <div className="counsellor-actions">
              <a className="chip" href={`tel:${c.phone.replace(/\s/g, '')}`}>
                <Phone size={15} aria-hidden="true" /> Call
              </a>
              <a className="chip" href={`mailto:${c.email}`}>
                <Mail size={15} aria-hidden="true" /> Email
              </a>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
