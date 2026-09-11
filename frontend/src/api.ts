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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
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
  created_at: string
}

export interface EntryResponse {
  entries: Entry[]
  reply: Message
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

export async function getEvents(): Promise<Entry[]> {
  return request<Entry[]>(`${BASE}/events`)
}
