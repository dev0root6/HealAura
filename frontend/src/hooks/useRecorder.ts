import { useCallback, useRef, useState } from 'react'

/** MIME types MediaRecorder might give us, best first. Sarvam accepts all three. */
const PREFERRED_TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined') return undefined
  return PREFERRED_TYPES.find((t) => MediaRecorder.isTypeSupported(t))
}

export interface Recorder {
  recording: boolean
  supported: boolean
  error: string | null
  start: () => Promise<void>
  stop: () => Promise<Blob | null>
  cancel: () => void
}

/** Microphone capture. The stream is always released, including on error. */
export function useRecorder(): Recorder {
  const [recording, setRecording] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  const release = useCallback(() => {
    recorderRef.current?.stream.getTracks().forEach((track) => track.stop())
    recorderRef.current = null
    chunksRef.current = []
    setRecording(false)
  }, [])

  const start = useCallback(async () => {
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream, { mimeType: pickMimeType() })
      chunksRef.current = []
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      recorder.start()
      recorderRef.current = recorder
      setRecording(true)
    } catch (err) {
      // Most often a denied mic permission, which is not worth a stack trace.
      setError(
        err instanceof DOMException && err.name === 'NotAllowedError'
          ? 'Microphone access was blocked.'
          : err instanceof Error
            ? err.message
            : String(err),
      )
      release()
    }
  }, [release])

  const stop = useCallback(async () => {
    const recorder = recorderRef.current
    if (!recorder) return null
    const blob = await new Promise<Blob>((resolve) => {
      recorder.onstop = () =>
        resolve(new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' }))
      recorder.stop()
    })
    release()
    return blob.size > 0 ? blob : null
  }, [release])

  return {
    recording,
    supported: typeof MediaRecorder !== 'undefined',
    error,
    start,
    stop,
    cancel: release,
  }
}
