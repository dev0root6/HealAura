export interface Entry {
  id: string
  raw_text: string
  segment_text: string
  entry_type: string
  sentiment: string
  event_date: string | null
  event_time: string | null
  person: string | null
  ai_confidence: number | null
  user_confirmed: number
  corrected_type: string | null
  corrected_sentiment: string | null
  alert_sent: boolean
  is_fallback: boolean
  message_id: string | null
  created_at: string
}

const BASE = ''

const TOKEN_KEY = 'healaura_token'

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage unavailable — stay in-memory only */
  }
}

/** Thrown on a 401 so the UI can bounce the user back to the login screen. */
export class AuthError extends Error {}

function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(init?.headers ?? {}) },
    ...init,
  })
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`
    try {
      const body = await resp.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* ignore non-JSON errors */
    }
    if (resp.status === 401) throw new AuthError(detail)
    throw new Error(detail)
  }
  return resp.json() as Promise<T>
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  kind: string
  needs_support: boolean
  /** Explicit self-harm / suicide disclosure: show crisis resources now. */
  crisis: boolean
  language_code: string | null
  created_at: string
}

export interface EntryResponse {
  entries: Entry[]
  reply: Message
}

export interface AudioEntryResponse extends EntryResponse {
  transcript: string
}

export async function submitEntry(rawText: string): Promise<EntryResponse> {
  return request<EntryResponse>(`${BASE}/entries`, {
    method: 'POST',
    body: JSON.stringify({ raw_text: rawText }),
  })
}

export async function getMessages(date?: string): Promise<Message[]> {
  const params = date ? `?date=${date}` : ''
  return request<Message[]>(`${BASE}/entries/messages${params}`)
}

export async function askForSuggestion(rawText: string): Promise<Message> {
  return request<Message>(`${BASE}/entries/suggest`, {
    method: 'POST',
    body: JSON.stringify({ raw_text: rawText }),
  })
}

export async function getEntries(date?: string): Promise<Entry[]> {
  const params = date ? `?date=${date}` : ''
  return request<Entry[]>(`${BASE}/entries${params}`)
}
export async function correctEntry(
  id: string,
  correction: { corrected_type?: string; corrected_sentiment?: string },
): Promise<Entry> {
  return request<Entry>(`${BASE}/entries/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(correction),
  })
}

export interface DayTrend {
  day: string
  positive: number
  negative: number
  neutral: number
  mixed: number
  total: number
  negative_share: number | null
  smoothed_negative: number | null
}

export interface Trends {
  days: DayTrend[]
  totals: Record<'positive' | 'negative' | 'neutral' | 'mixed', number>
}

export async function getTrends(days = 30): Promise<Trends> {
  return request<Trends>(`${BASE}/entries/trends?days=${days}`)
}

export async function getEvents(): Promise<Entry[]> {
  return request<Entry[]>(`${BASE}/events`)
}

export async function submitAudio(blob: Blob): Promise<AudioEntryResponse> {
  const form = new FormData()
  // The extension matters to the API's format sniffing, so keep it in step
  // with whatever MIME type MediaRecorder actually gave us.
  const ext = blob.type.includes('ogg') ? 'ogg' : blob.type.includes('mp4') ? 'mp4' : 'webm'
  form.append('file', blob, `entry.${ext}`)

  const resp = await fetch(`${BASE}/entries/audio`, {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  })
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`
    try {
      const body = await resp.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* ignore non-JSON errors */
    }
    throw new Error(detail)
  }
  return resp.json() as Promise<AudioEntryResponse>
}

// --- auth ---
export interface User {
  id: string
  username: string
  email: string | null
  created_at: string
}

/** Sign in with a username or the registered email. */
export async function login(login: string, password: string): Promise<{ token: string; user: User }> {
  const res = await request<{ token: string; user: User }>(`${BASE}/auth/login`, {
    method: 'POST',
    body: JSON.stringify({ username: login, password }),
  })
  setToken(res.token)
  return res
}

// --- sign-up: email code -> verify -> username & password ---
export async function startRegistration(
  email: string,
): Promise<{ delivery: 'email' | 'log'; expires_in_minutes: number }> {
  return request(`${BASE}/auth/register/start`, {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

export async function verifyRegistration(email: string, code: string): Promise<{ signup_token: string }> {
  return request(`${BASE}/auth/register/verify`, {
    method: 'POST',
    body: JSON.stringify({ email, code }),
  })
}

export async function completeRegistration(
  signupToken: string,
  username: string,
  password: string,
): Promise<{ token: string; user: User }> {
  const res = await request<{ token: string; user: User }>(`${BASE}/auth/register/complete`, {
    method: 'POST',
    body: JSON.stringify({ signup_token: signupToken, username, password }),
  })
  setToken(res.token)
  return res
}

export async function logout(): Promise<void> {
  try {
    await request(`${BASE}/auth/logout`, { method: 'POST' })
  } catch {
    /* best effort */
  }
  setToken(null)
}

export async function fetchMe(): Promise<User> {
  return request<User>(`${BASE}/auth/me`)
}

// --- close friends ---
export interface Friend {
  id: string
  name: string
  email: string
  created_at: string
}

export async function listFriends(): Promise<Friend[]> {
  return request<Friend[]>(`${BASE}/friends`)
}

export async function addFriend(name: string, email: string): Promise<Friend> {
  return request<Friend>(`${BASE}/friends`, {
    method: 'POST',
    body: JSON.stringify({ name, email }),
  })
}

export async function deleteFriend(id: string): Promise<void> {
  await request(`${BASE}/friends/${id}`, { method: 'DELETE' })
}

// --- counsellors ---
export interface Counsellor {
  name: string
  title: string
  languages: string[]
  phone: string
  email: string
  available: string
}

export async function getCounsellors(): Promise<Counsellor[]> {
  return request<Counsellor[]>(`${BASE}/counsellors`)
}

// --- community (channels) ---
export interface Channel {
  id: string
  slug: string
  name: string
  description: string
  is_default: boolean
  created_at: string
  last_message_at: string | null
  message_count: number
}

export interface CommunityMessage {
  id: string
  channel_id: string | null
  handle: string
  content: string
  /** Written by one of HealAura's AI companions; always labelled in the UI. */
  is_bot: boolean
  reply_to: string | null
  created_at: string
}

export async function getChannels(): Promise<Channel[]> {
  return request<Channel[]>(`${BASE}/community/channels`)
}

export async function createChannel(name: string, description: string): Promise<Channel> {
  return request<Channel>(`${BASE}/community/channels`, {
    method: 'POST',
    body: JSON.stringify({ name, description }),
  })
}

export async function getChannelMessages(channelId: string): Promise<CommunityMessage[]> {
  return request<CommunityMessage[]>(`${BASE}/community/channels/${channelId}/messages`)
}

export async function postChannelMessage(channelId: string, content: string): Promise<CommunityMessage> {
  return request<CommunityMessage>(`${BASE}/community/channels/${channelId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  })
}

export async function getMyHandle(): Promise<string> {
  return (await request<{ handle: string }>(`${BASE}/community/me`)).handle
}

/** URL of the live community socket on the same origin (works behind the Vite proxy and tunnels). */
export function communitySocketUrl(): string {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${window.location.host}/community/ws`
}

/** Fetches spoken audio for a reply. Returns an object URL the caller owns. */
export interface VoiceOption {
  id: string
  label: string
  family: 'Indian' | 'International'
  gender: 'f' | 'm'
  /** False when the engine behind it can't be used right now (e.g. not enabled on the server). */
  available: boolean
}

export async function getVoices(): Promise<VoiceOption[]> {
  return request<VoiceOption[]>(`${BASE}/entries/voices`)
}

export async function speak(
  text: string,
  languageCode: string | null,
  options: { voice?: string; tone?: 'warm' | 'gentle' } = {},
): Promise<string> {
  const resp = await fetch(`${BASE}/entries/speech`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ text, language_code: languageCode, voice: options.voice, tone: options.tone }),
  })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return URL.createObjectURL(await resp.blob())
}
