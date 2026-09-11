import { useCallback, useEffect, useRef, useState } from 'react'
import { speak } from '../api'
import type { Message } from '../api'

const STORAGE_KEY = 'healaura:voice-reply'

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

  const play = useCallback(
    async (message: Message) => {
      if (!enabled) return
      try {
        cleanup()
        const url = await speak(message.content, message.language_code)
        urlRef.current = url
        const audio = new Audio(url)
        audioRef.current = audio
        await audio.play()
      } catch {
        // A reply that cannot be spoken is still on screen — stay silent
        // rather than interrupting with an error.
      }
    },
    [cleanup, enabled],
  )

  return { enabled, toggle, play }
}
