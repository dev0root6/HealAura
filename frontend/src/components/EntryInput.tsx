import { useState } from 'react'
import type { FormEvent } from 'react'
import type { Entry } from '../api'

interface EntryInputProps {
  onSubmit: (rawText: string) => Promise<Entry[]>
  onSubmitted: (entries: Entry[]) => void
}

export default function EntryInput({ onSubmit, onSubmitted }: EntryInputProps) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const raw = text.trim()
    if (!raw || busy) return
    setBusy(true)
    setError(null)
    try {
      const entries = await onSubmit(raw)
      onSubmitted(entries)
      setText('')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="entry-input">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="How did your day go? (English / Tamil / Hindi / Tanglish / Hinglish)"
        rows={3}
        disabled={busy}
      />
      <button type="submit" disabled={busy || !text.trim()}>
        {busy ? 'Classifying…' : 'Submit'}
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  )
}