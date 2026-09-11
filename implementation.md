# implementation.md

## Stack (v1 — web app)

- **Frontend:** React (Vite) + TSX, plain fetch calls — no framework overkill for a demo
- **Backend:** FastAPI (Python), async endpoints (`async def` + `httpx.AsyncClient` for Sarvam calls, not `requests`)
- **Database:** Neon (hosted Postgres)
- **Background jobs:** FastAPI `BackgroundTasks` (fire-and-forget, e.g. STT processing) + APScheduler (in-process scheduled job for checking due reminders/alerts) — no Celery/Redis for this scope
- **AI:**
  - Classification / sentiment / NER: Sarvam-105B via `/v1/chat/completions` (OpenAI-compatible)
  - STT (stretch goal): Sarvam Saaras v3 via `/speech-to-text`
  - Conversational AI (stretch goal): Sarvam chat endpoint, separate from the classification calls
- **Env/secrets:** `.env` for `SARVAM_API_KEY` and `NEON_DATABASE_URL`, never committed

## Directory Structure

```
~/Projects/<project-name>/
├── backend/
│   ├── main.py                # FastAPI app entrypoint, starts APScheduler on startup
│   ├── db.py                  # Neon/Postgres connection (SQLAlchemy or asyncpg) + schema init
│   ├── sarvam_client.py       # Wraps Sarvam API calls (chat + STT), async httpx client
│   ├── classify.py            # Segmentation + prompt construction + response parsing
│   ├── models.py               # Pydantic schemas for entries/events
│   ├── scheduler.py           # APScheduler job: checks due events, triggers alerts
│   └── routes/
│       ├── entries.py         # POST /entries, GET /entries?date=
│       └── events.py          # GET /events (reminders)
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── EntryInput.tsx
│   │   │   ├── EntryList.tsx      # today's classified entries
│   │   │   ├── EntryCard.tsx      # single entry, with confirm/correct control
│   │   │   └── ReminderList.tsx
│   │   └── api.ts             # fetch wrappers to backend
├── .env
└── requirements.txt
```

## Data Model

```sql
CREATE TABLE entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_text TEXT NOT NULL,        -- original submitted segment source text
    segment_text TEXT NOT NULL,    -- this specific clause/sentence
    entry_type TEXT NOT NULL,      -- 'memory' | 'event' | 'task'
    sentiment TEXT NOT NULL,       -- 'positive' | 'negative' | 'neutral' | 'mixed'
    event_date DATE,               -- nullable, extracted date
    event_time TIME,               -- nullable
    person TEXT,                   -- nullable, extracted name/role
    ai_confidence REAL,            -- optional, if model returns it
    user_confirmed SMALLINT DEFAULT 0,  -- 0 = unreviewed, 1 = confirmed, 2 = corrected
    corrected_type TEXT,           -- if user overrides entry_type
    corrected_sentiment TEXT,      -- if user overrides sentiment
    alert_sent BOOLEAN DEFAULT FALSE,   -- set by scheduler once a reminder/alert fires
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Postgres syntax (Neon). Keep it flat and simple for v1 — no separate `users` table needed if this is single-user for the demo.

## Sarvam Integration

### Classification call (core of the pipeline)

Endpoint: `https://api.sarvam.ai/v1/chat/completions`, model `sarvam-105b`.

**System prompt (draft — iterate on this):**
```
You are a segmentation and classification engine for a daily journaling app.
Input: a short daily entry, possibly in English, Tamil, Hindi, or code-mixed
(Tanglish/Hinglish).

Steps:
1. Split the input into distinct segments — each segment should cover one
   topic, memory, event, or task. A single sentence can contain more than
   one segment if it shifts topic (e.g. "X happened, also Y is tomorrow").
2. For each segment, classify:
   - type: "memory" (something that already happened, no action needed),
     "event" (has a specific date/time to be scheduled), or
     "task" (something the user says they need/plan to do, no fixed date/time)
   - sentiment: "positive", "negative", "neutral", or "mixed"
     - Base sentiment on evaluative language (e.g. "was great", "felt bad",
       "suvaiaa irundhichu"), NOT on the topic alone. A neutral fact
       ("I ate biryani") is neutral unless an opinion is attached
       ("it was tasty" -> positive).
   - date: ISO date if mentioned or inferable (e.g. "tomorrow"), else null
   - time: extracted time if present, else null
   - person: name or relation mentioned (e.g. "GF", "placement cell"), else null

Respond ONLY with a JSON array, no preamble, no markdown fences:
[
  {"segment_text": "...", "type": "...", "sentiment": "...",
   "date": "...", "time": "...", "person": "..."}
]
```

**Few-shot examples to include in the prompt (from testing so far):**
- "naan inaiki biryani sapten" → memory, neutral (plain fact, no evaluative language)
- "naan inaiki biryani sapten, athu suvaiaa irundhichu" → memory, positive (evaluative language attached)
- "nalaiki en GF oda meeting iruku" → event, neutral, date=tomorrow, person=GF
- "ellarum app pathi paratunanga aana enakku incomplete-aa irundhichu, so inum develop pananum" → task, mixed/negative (dissatisfaction is the dominant signal), no date

### Parsing the response
- Always parse with `try/except json.loads`, strip markdown fences defensively even though the prompt says not to include them (models occasionally add them anyway)
- Validate each object against the Pydantic schema before storing — drop/log malformed segments rather than crashing the whole request

### Error handling
- Sarvam API failures (rate limit, timeout) → return a clear error to frontend, do not silently store an empty/broken entry
- If JSON parsing fails entirely, store the raw entry as a single `type: "memory"`, `sentiment: "neutral"` fallback, flagged `ai_confidence: null` so the UI can visually indicate "unclassified, please review"

## Confirm/Correct Flow
- Each `EntryCard` shows the AI's type + sentiment as editable dropdowns/pills
- On user edit: `PATCH /entries/{id}` sets `user_confirmed = 2`, stores `corrected_type`/`corrected_sentiment`
- On simple confirm (no edit): `PATCH /entries/{id}` sets `user_confirmed = 1`
- Log corrections separately (even just a CSV/JSON export) — this becomes your few-shot/fine-tuning dataset later

## Reminders (v1, simplified)
- `GET /events?upcoming=true` — returns all entries where `type = 'event'` and `event_date` is set, sorted by date
- Display as a simple card list in the frontend for now
- Scheduler-driven alerts (see Background Processing below) supplement this list with an actual notification at/near the due time

## Background Processing

### FastAPI `BackgroundTasks`
Use for fire-and-forget work triggered by a request but not needed for the response — e.g. once STT is wired in, accept the audio upload, return immediately, and transcribe in the background rather than blocking the request.

```python
@app.post("/entries/audio")
async def submit_audio(file: UploadFile, background_tasks: BackgroundTasks):
    audio_id = save_upload(file)
    background_tasks.add_task(process_audio_entry, audio_id)
    return {"status": "processing", "id": audio_id}
```

### APScheduler (in-process, no external queue)
Runs a recurring job inside the FastAPI process itself — no Celery/Redis needed at this scale.

```python
# scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

def start_scheduler():
    scheduler.add_job(check_due_events, "interval", minutes=1)
    scheduler.start()

async def check_due_events():
    due = await db.fetch_due_events()  # event_date/time <= now, alert_sent = false
    for event in due:
        await trigger_alert(event)     # in-app notification for v1; contact-alert flow deferred
        await db.mark_alert_sent(event.id)
```

Called from `main.py` on startup (`@app.on_event("startup")`).

**Scope boundary:** this scheduler only handles *self*-notifications (reminding the user of their own event) for v1. The contact-alert-with-verification feature described in PLAN.md is a separate, deferred piece — do not wire the scheduler directly to sending alerts to third-party contacts without the verification step built first.

**If this needs to scale later:** move to Celery + Redis (or a hosted queue) only if job volume, retries-on-failure, or multi-instance deployment become real requirements — not before.

## What's Deliberately Not Built Yet
- No on-device storage / encryption — entries live on Neon (hosted Postgres), plainly not privacy-hardened yet. Document this honestly in the pitch.
- No contact-alert/verification flow — scheduler only self-notifies for now; if the contact-alert feature is demoed, it must be clearly labeled as a mockup/roadmap item, not working functionality
- No voice input pipeline — text only until STT is wired in as a stretch goal
- No conversational AI screen — stretch goal only, must remain clearly separate/opt-in even once built, per the "no default chatbot" design principle

## Dev Notes
- Test Sarvam prompt changes against a fixed set of the example sentences above before/after any prompt edit — keep a small `test_cases.json` so regressions are visible
- Keep segmentation and classification in a single Sarvam call for now (cost/latency reasons) — revisit as two separate calls only if single-call accuracy proves unreliable
