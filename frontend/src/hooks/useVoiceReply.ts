import { useCallback, useEffect, useRef, useState } from 'react'
import { getVoices, speak } from '../api'
import type { Message, VoiceOption } from '../api'

const STORAGE_KEY = 'healaura:voice-reply'
const VOICE_KEY = 'healaura:voice'

const DEFAULT_VOICE = 'ishita'

function readVoice(): string {
  try {
    return localStorage.getItem(VOICE_KEY) || DEFAULT_VOICE
  } catch {
    return DEFAULT_VOICE
  }
}

function readPreference(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'on'
  } catch {
    // Private windows and blocked site data both throw here.
    return false
  }
}

/** Speaks assistant replies aloud, when the user has asked for that. */
export function useVoiceReply() {
  const [enabled, setEnabled] = useState(readPreference)
  const [voice, setVoiceState] = useState(readVoice)
  // The server owns the voice list and knows which engines are usable.
  const [voices, setVoices] = useState<VoiceOption[]>([])

  useEffect(() => {
    if (!enabled || voices.length) return
    getVoices()
      .then(setVoices)
      .catch(() => {
        /* picker just stays empty; replies still use the server default */
      })
  }, [enabled, voices.length])
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const urlRef = useRef<string | null>(null)

  const cleanup = useCallback(() => {
    audioRef.current?.pause()
    audioRef.current = null
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current)
      urlRef.current = null
    }
  }, [])

  useEffect(() => cleanup, [cleanup])

  const toggle = useCallback(() => {
    setEnabled((prev) => {
      const next = !prev
      try {
        localStorage.setItem(STORAGE_KEY, next ? 'on' : 'off')
      } catch {
        /* preference just won't persist */
      }
      if (!next) cleanup()
      return next
    })
  }, [cleanup])

  const setVoice = useCallback((id: string) => {
    setVoiceState(id)
    try {
      localStorage.setItem(VOICE_KEY, id)
    } catch {
      /* preference just won't persist */
    }
  }, [])

  const play = useCallback(
    async (message: Message) => {
      if (!enabled) return
      try {
        cleanup()
        // Heavier moments get a softer delivery.
        const tone = message.needs_support || message.crisis ? 'gentle' : 'warm'
        const url = await speak(message.content, message.language_code, { voice, tone })
        urlRef.current = url
        const audio = new Audio(url)
        audioRef.current = audio
        await audio.play()
      } catch {
        // A reply that cannot be spoken is still on screen — stay silent
        // rather than interrupting with an error.
      }
    },
    [cleanup, enabled, voice],
  )

  return { enabled, toggle, play, voice, setVoice, voices }
}
