import { useCallback, useEffect, useRef, useState } from 'react'

/** MIME types MediaRecorder might give us, best first. Sarvam accepts all of them. */
const PREFERRED_TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']

// Tuning: a turn ends after this much silence following speech.
const END_OF_TURN_MS = 2000
// Ignore blips shorter than this (a cough, a click).
const MIN_SPEECH_MS = 450
// While nobody speaks, the recording is restarted this often so old silence isn't kept.
const IDLE_RESTART_MS = 8000
const TICK_MS = 50
const CALIBRATE_MS = 600

export type LiveState = 'off' | 'starting' | 'listening' | 'hearing' | 'thinking' | 'speaking'

interface Options {
  /** Handle one spoken turn: send it, show the reply, speak it. Resolve when the reply has finished playing. */
  onUtterance: (audio: Blob, setPhase: (s: 'thinking' | 'speaking') => void) => Promise<void>
}

/**
 * Hands-free conversation: listens continuously, and when the person pauses
 * for 2 seconds after speaking, sends what they said and plays the reply.
 * The mic is paused while HealAura thinks and speaks, so it never hears itself.
 */
export function useLiveVoice({ onUtterance }: Options) {
  const [state, setState] = useState<LiveState>('off')
  const [error, setError] = useState<string | null>(null)
  const [level, setLevel] = useState(0)

  const streamRef = useRef<MediaStream | null>(null)
  const ctxRef = useRef<AudioContext | null>(null)
  const recRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const busyRef = useRef(false)
  const activeRef = useRef(false)
  const onUtteranceRef = useRef(onUtterance)
  onUtteranceRef.current = onUtterance

  const mimeType =
    typeof MediaRecorder !== 'undefined'
      ? PREFERRED_TYPES.find((t) => MediaRecorder.isTypeSupported(t))
      : undefined

  const startRecorder = useCallback(() => {
    const stream = streamRef.current
    if (!stream) return
    const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    chunksRef.current = []
    rec.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data)
    }
    rec.start()
    recRef.current = rec
  }, [mimeType])

  const stopRecorder = useCallback(
    () =>
      new Promise<Blob | null>((resolve) => {
        const rec = recRef.current
        recRef.current = null
        if (!rec || rec.state === 'inactive') return resolve(null)
        rec.onstop = () => resolve(new Blob(chunksRef.current, { type: rec.mimeType || 'audio/webm' }))
        rec.stop()
      }),
    [],
  )

  const stop = useCallback(() => {
    activeRef.current = false
    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = null
    const rec = recRef.current
    recRef.current = null
    if (rec && rec.state !== 'inactive') rec.stop()
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    ctxRef.current?.close().catch(() => {})
    ctxRef.current = null
    busyRef.current = false
    setLevel(0)
    setState('off')
  }, [])

  const start = useCallback(async () => {
    if (activeRef.current) return
    setError(null)
    setState('starting')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      })
      streamRef.current = stream
      const ctx = new AudioContext()
      ctxRef.current = ctx
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 1024
      ctx.createMediaStreamSource(stream).connect(analyser)
      const buf = new Float32Array(analyser.fftSize)

      activeRef.current = true
      startRecorder()
      setState('listening')

      const startedAt = performance.now()
      let floor = 0
      let floorSamples = 0
      let threshold = 0.02
      let speechStart = 0
      let lastVoice = 0
      let segmentStart = performance.now()

      timerRef.current = setInterval(async () => {
        if (!activeRef.current || busyRef.current) return
        analyser.getFloatTimeDomainData(buf)
        let sum = 0
        for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i]
        const rms = Math.sqrt(sum / buf.length)
        setLevel(Math.min(1, rms * 12))
        const now = performance.now()

        // Learn the room's background level first, then listen above it.
        if (now - startedAt < CALIBRATE_MS) {
          floor = (floor * floorSamples + rms) / ++floorSamples
          threshold = Math.max(0.015, floor * 3)
          return
        }

        if (rms > threshold) {
          if (!speechStart) {
            speechStart = now
            setState('hearing')
          }
          lastVoice = now
          return
        }

        if (speechStart && now - lastVoice > END_OF_TURN_MS) {
          const spoke = lastVoice - speechStart
          speechStart = 0
          busyRef.current = true
          const blob = await stopRecorder()
          if (blob && blob.size > 0 && spoke >= MIN_SPEECH_MS) {
            setState('thinking')
            try {
              await onUtteranceRef.current(blob, (s) => setState(s))
            } catch (err) {
              setError(err instanceof Error ? err.message : String(err))
            }
          }
          if (!activeRef.current) return
          startRecorder()
          segmentStart = performance.now()
          busyRef.current = false
          setState('listening')
          return
        }

        // Long quiet stretch with no speech: start a fresh recording.
        if (!speechStart && now - segmentStart > IDLE_RESTART_MS) {
          busyRef.current = true
          await stopRecorder()
          if (activeRef.current) startRecorder()
          segmentStart = performance.now()
          busyRef.current = false
        }
      }, TICK_MS)
    } catch (err) {
      stop()
      setError(
        err instanceof DOMException && err.name === 'NotAllowedError'
          ? 'Microphone access was blocked.'
          : err instanceof Error
            ? err.message
            : String(err),
      )
    }
  }, [startRecorder, stopRecorder, stop])

  useEffect(() => stop, [stop])

  return {
    state,
    active: state !== 'off',
    level,
    error,
    supported: typeof MediaRecorder !== 'undefined' && !!navigator.mediaDevices,
    start,
    stop,
  }
}
