import { AudioLines, Mic, PhoneOff, Square } from 'lucide-react'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { submitAudio, submitEntry } from '../api'
import type { ChatMode, EntryResponse } from '../api'
import { useLiveVoice } from '../hooks/useLiveVoice'
import { useRecorder } from '../hooks/useRecorder'

interface EntryInputProps {
  mode: ChatMode
  /** Show the turn and reply; resolves when any spoken reply has finished. */
  onSubmitted: (response: EntryResponse, rawText: string, options?: { live?: boolean }) => Promise<void> | void
}

const LIVE_LABEL: Record<string, string> = {
  starting: 'Starting the mic…',
  listening: 'Listening… just talk. A 2-second pause sends it.',
  hearing: "I'm listening…",
  thinking: 'Thinking…',
  speaking: 'Speaking…',
}

export default function EntryInput({ mode, onSubmitted }: EntryInputProps) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const recorder = useRecorder()
  const live = useLiveVoice({
    onUtterance: async (blob, setPhase) => {
      const response = await submitAudio(blob, mode)
      setPhase('speaking')
      await onSubmitted(response, response.transcript, { live: true })
    },
  })

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const raw = text.trim()
    if (!raw || busy) return
    setBusy(true)
    setError(null)
    try {
      const response = await submitEntry(raw, mode)
      await onSubmitted(response, raw)
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
      const response = await submitAudio(blob, mode)
      await onSubmitted(response, response.transcript)
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
        disabled={busy || recorder.recording || live.active}
      />
      {live.active && (
        <div className={`live-status ${live.state}`} role="status">
          <span className="live-meter" aria-hidden="true">
            {[0.15, 0.35, 0.6, 0.35, 0.15].map((w, i) => (
              <i key={i} style={{ transform: `scaleY(${0.25 + Math.min(1, live.level * (1 + w * 3))})` }} />
            ))}
          </span>
          {LIVE_LABEL[live.state] ?? ''}
        </div>
      )}
      <div className="input-actions">
        {live.supported && (
          <button
            type="button"
            className={`mic live${live.active ? ' recording' : ''}`}
            onClick={live.active ? live.stop : live.start}
            disabled={busy || recorder.recording}
            aria-pressed={live.active}
            title="Hands-free: talk naturally, pause for 2 seconds and HealAura answers"
          >
            {live.active ? (
              <>
                <PhoneOff size={15} aria-hidden="true" /> End live talk
              </>
            ) : (
              <>
                <AudioLines size={16} aria-hidden="true" /> Live talk
              </>
            )}
          </button>
        )}
        {recorder.supported && !live.active && (
          <button
            type="button"
            className={`mic${recorder.recording ? ' recording' : ''}`}
            onClick={handleMic}
            disabled={busy}
            aria-label={recorder.recording ? 'Stop recording' : 'Record your entry'}
            aria-pressed={recorder.recording}
          >
            {recorder.recording ? (
              <>
                <Square size={14} aria-hidden="true" /> Stop
              </>
            ) : (
              <>
                <Mic size={16} aria-hidden="true" /> Talk
              </>
            )}
          </button>
        )}
        <button type="submit" disabled={busy || recorder.recording || live.active || !text.trim()}>
          {busy ? 'Listening…' : 'Tell'}
        </button>
      </div>
      {recorder.recording && <p className="muted recording-hint">Recording… tap stop when done.</p>}
      {(error || recorder.error || live.error) && (
        <p className="error">{error ?? recorder.error ?? live.error}</p>
      )}
    </form>
  )
}
