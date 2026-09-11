import { useState } from 'react'
import type { FormEvent } from 'react'
import { submitAudio } from '../api'
import type { EntryResponse } from '../api'
import { useRecorder } from '../hooks/useRecorder'

interface EntryInputProps {
  onSubmit: (rawText: string) => Promise<EntryResponse>
  onSubmitted: (response: EntryResponse, rawText: string) => void
}

export default function EntryInput({ onSubmit, onSubmitted }: EntryInputProps) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const recorder = useRecorder()

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const raw = text.trim()
    if (!raw || busy) return
    setBusy(true)
    setError(null)
    try {
      const response = await onSubmit(raw)
      onSubmitted(response, raw)
      setText('')
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function handleMic() {
    if (busy) return
    if (!recorder.recording) {
      await recorder.start()
      return
    }

    const blob = await recorder.stop()
    if (!blob) return
    setBusy(true)
    setError(null)
    try {
      const response = await submitAudio(blob)
      onSubmitted(response, response.transcript)
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
        disabled={busy || recorder.recording}
      />
      <div className="input-actions">
        {recorder.supported && (
          <button
            type="button"
            className={`mic${recorder.recording ? ' recording' : ''}`}
            onClick={handleMic}
            disabled={busy}
            aria-label={recorder.recording ? 'Stop recording' : 'Record your entry'}
            aria-pressed={recorder.recording}
          >
            {recorder.recording ? '■ Stop' : '🎙 Talk'}
          </button>
        )}
        <button type="submit" disabled={busy || recorder.recording || !text.trim()}>
          {busy ? 'Listening…' : 'Tell'}
        </button>
      </div>
      {recorder.recording && <p className="muted recording-hint">Recording… tap stop when done.</p>}
      {(error || recorder.error) && <p className="error">{error ?? recorder.error}</p>}
    </form>
  )
}
