import { useCallback, useEffect, useRef, useState } from 'react'
import { communitySocketUrl, getToken } from '../api'
import type { Channel, CommunityMessage } from '../api'

export interface CommunityEvents {
  onMessage: (message: CommunityMessage) => void
  onChannel: (channel: Channel) => void
  onTyping: (handle: string, channelId: string) => void
}

export type LiveStatus = 'connecting' | 'live' | 'offline'

/**
 * One WebSocket for the whole community: new messages in every channel,
 * new channels, who's typing, and who's online. Reconnects with backoff.
 */
export function useCommunitySocket(viewingChannel: string | null, events: CommunityEvents) {
  const [status, setStatus] = useState<LiveStatus>('connecting')
  const [online, setOnline] = useState(0)
  const [perChannel, setPerChannel] = useState<Record<string, number>>({})
  const [handle, setHandle] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const eventsRef = useRef(events)
  const viewingRef = useRef(viewingChannel)
  eventsRef.current = events
  viewingRef.current = viewingChannel

  useEffect(() => {
    let closed = false
    let retry = 0
    let timer: ReturnType<typeof setTimeout> | undefined

    function connect() {
      setStatus('connecting')
      const ws = new WebSocket(communitySocketUrl())
      wsRef.current = ws
      ws.onopen = () => {
        retry = 0
        ws.send(JSON.stringify({ type: 'auth', token: getToken() }))
        if (viewingRef.current) ws.send(JSON.stringify({ type: 'view', channel_id: viewingRef.current }))
      }
      ws.onmessage = (e) => {
        let ev: Record<string, unknown>
        try {
          ev = JSON.parse(e.data)
        } catch {
          return
        }
        switch (ev.type) {
          case 'hello':
            setHandle(ev.handle as string)
            setStatus('live')
            break
          case 'message':
            eventsRef.current.onMessage(ev.message as CommunityMessage)
            break
          case 'channel':
            eventsRef.current.onChannel(ev.channel as Channel)
            break
          case 'typing':
            eventsRef.current.onTyping(ev.handle as string, ev.channel_id as string)
            break
          case 'presence':
            setOnline(ev.online as number)
            setPerChannel((ev.channels as Record<string, number>) ?? {})
            break
        }
      }
      ws.onclose = (e) => {
        // Only forget this socket if it is still the current one; a stale
        // socket closing late (e.g. StrictMode's remount) must not clear the
        // live one.
        if (wsRef.current === ws) wsRef.current = null
        if (closed) return
        setStatus('offline')
        if (e.code === 4401) return // signed out; don't hammer the server
        retry = Math.min(retry + 1, 6)
        timer = setTimeout(connect, 1000 * 2 ** (retry - 1))
      }
    }

    connect()
    return () => {
      closed = true
      clearTimeout(timer)
      wsRef.current?.close()
    }
  }, [])

  // Tell the server which channel this tab shows (presence + typing scope).
  useEffect(() => {
    const ws = wsRef.current
    if (viewingChannel && ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'view', channel_id: viewingChannel }))
    }
  }, [viewingChannel, status])

  const sendTyping = useCallback(() => {
    const ws = wsRef.current
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'typing' }))
  }, [])

  return { status, online, perChannel, handle, sendTyping }
}
