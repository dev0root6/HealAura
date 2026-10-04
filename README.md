# HealAura

An AI-assisted daily reflection web app that helps reduce the impact of stress (it is a reflection aid, not a medical treatment).

You write — or speak — a short daily entry. HealAura segments it into clauses, classifies each segment as a **memory**, **event**, or **task**, tags sentiment, and extracts any date, time, or person mentioned. Entries are stored, shown back to you, and correctable with a single edit. Events that carry a date/time become reminders. Voice entries can be spoken in and answered back with a short spoken reply.

The app sits behind a login (public landing page → sign in → app). Once inside, four ways to reach out:

1. **Talk with AI** — the daily reflection journal. Choose **Short** replies (a few listening words) or **Conversation** (HealAura reflects, remembers today's earlier turns and asks a follow-up question). **Live talk** is hands-free: just speak, and a 2-second pause sends it; the reply is spoken and HealAura listens again.
2. **Community** — Discord-style channels (`#general`, `#exam-stress`, `#placements`, `#late-night`, `#small-wins`, `#vent`, plus any a user creates), real-time over a WebSocket: instant messages, typing indicators, who's-here counts, unread and @mention badges. Everyone picks a unique **community alias**; `@alias` notifies that person live, and `@HealAura` asks the AI (which also always answers crisis posts and sometimes greets a post in a quiet channel). Images can be shared (re-encoded, location data stripped). **Messages and images disappear after 24 hours.**
3. **Counsellors** — a directory of counsellors to call or email (demo data).
4. **Close friends** — you add people you trust. A background *well-being agent* watches your recent reflections and, **only** when it detects sustained distress (or an explicit crisis), emails you a check-in with helplines and nudges those friends to check in on you. It never shares what you wrote.

Plus **My trends** (daily sentiment and a smoothed "heaviness" line) and an immediate crisis card with helplines when an entry mentions self-harm.

**Profile:** after sign-up (and for older accounts, via a "Finish setting up your account" prompt) people set what HealAura should call them, the language they speak, their interests, and a verified email if they don't have one. HealAura always replies in the language the person writes in; the chosen language is the fallback. `backend/send_setup_reminders.py` emails older accounts once to finish setup.

**Accounts are self-registered.** Sign up with your email → HealAura emails a 6-digit code → enter it → choose a username and password. Sign in with either the username or the email. Journal data is per-user and private to each account. (Without SMTP configured, the code is written to the backend log so sign-up can still be tested.)

## Architecture

- **Backend** — [FastAPI](https://fastapi.tiangolo.com/) (Python), served with Uvicorn. Persists to Neon (hosted Postgres) via `asyncpg`. Uses [Sarvam AI](https://www.sarvam.ai/) for classification/sentiment/NER (Sarvam-105B), speech-to-text (Saaras v3, handles code-mixed Tanglish/Hinglish), and text-to-speech (Bulbul v3). Background reminder checks run in-process via the scheduler.
- **Frontend** — React 19 + TypeScript, built with [Vite](https://vitejs.dev/). Talks to the backend through Vite's dev proxy.

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- A [Neon](https://neon.tech/) Postgres database (or any Postgres reachable over `postgresql://`)
- A [Sarvam AI](https://www.sarvam.ai/) API key

## Configuration

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

| Variable | Required | Description |
| --- | --- | --- |
| `SARVAM_API_KEY` | yes | Sarvam AI API key |
| `NEON_DATABASE_URL` | yes | Postgres connection string (`?sslmode=require` for Neon) |
| `SARVAM_STT_MODEL` | no | Speech-to-text model (default `saaras:v3`) |
| `SARVAM_STT_MODE` | no | STT mode (default `codemix`) |
| `SARVAM_TTS_MODEL` | no | Text-to-speech model (default `bulbul:v3`) |
| `SARVAM_TTS_SPEAKER` | no | Fallback TTS voice (default `ishita`; users pick a voice in the app) |
| `SARVAM_TTS_LANGUAGE` | no | TTS language (default `en-IN`) |
| `SMTP_USER` | for email | HealAura's Gmail address: sends sign-up codes and well-being check-ins |
| `SMTP_PASSWORD` | for alerts | Gmail **app password** (needs 2FA enabled; not your account password) |
| `SMTP_HOST` / `SMTP_PORT` | no | Defaults `smtp.gmail.com` / `587` |
| `SMTP_FROM_NAME` | no | Sender display name (default `HealAura`) |
| `GROQ_API_KEY` (or `GROQ_API`) | for companions | Groq key: community companions, and expressive English voice (Orpheus) |
| `GROQ_CHAT_MODEL` | no | Companion model (default `openai/gpt-oss-20b`) |
| `COMMUNITY_COMPANIONS` | no | `0` turns companions off (default on) |
| `COMMUNITY_COMPANIONS_PER_10MIN` | no | Cap on companion replies per 10 minutes (default `12`) |
| `CONFIDENCE_SAMPLES` | no | Extra classification samples per entry for the confidence score (default `2`; `0` disables). Each is one more Sarvam call |

Without `SMTP_USER` / `SMTP_PASSWORD` the app runs fine — the well-being agent just skips the email step.

## Running locally

The backend and frontend run as two processes.

### 1. Backend (port 8000)

```bash
python -m venv .venv          # first time only
source .venv/bin/activate
pip install -r requirements.txt   # first time only
cd backend
uvicorn main:app --reload --port 8000
```

The database schema is created automatically on startup. Check `http://127.0.0.1:8000/health` to confirm the backend and database are up.

### 2. Frontend (port 5173)

In a second terminal:

```bash
cd frontend
npm install                   # first time only
npm run dev
```

Open **http://localhost:5173**. (Cloudflare quick tunnels on `*.trycloudflare.com` are allowed by `vite.config.ts`. Run the API as a single worker, since the live community room is in-process.) The Vite dev server proxies `/entries`, `/events`, and `/health` to the backend at `127.0.0.1:8000`.

## API overview

Interactive API docs are available at `http://127.0.0.1:8000/docs` while the backend runs.

| Method | Path | Purpose |
| --- | --- | --- |
All endpoints except `/health`, `/auth/login` and `/auth/register/*` require an `Authorization: Bearer <token>` header (the token comes from login). Journal, event and friend endpoints act only on the authenticated user.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Backend and database health check |
| `POST` | `/auth/login` | Log in, returns a bearer token |
| `POST` | `/auth/logout` | Invalidate the current token |
| `GET` | `/auth/me` | Current user |
| `POST` | `/auth/register/start` | Email a 6-digit verification code |
| `POST` | `/auth/register/verify` | Check the code, returns a short-lived sign-up token |
| `POST` | `/auth/register/complete` | Choose username + password, returns a bearer token |
| `POST` | `/entries` | Submit a text entry (`mode`: `short` or `long`) |
| `GET` | `/entries?date=` | List the user's entries (optionally filtered by day) |
| `PATCH` | `/entries/{id}` | Correct an entry's classification |
| `GET` | `/entries/messages` | Fetch the conversation thread |
| `GET` | `/entries/trends?days=` | Daily sentiment counts and smoothed heaviness score |
| `POST` | `/entries/suggest` | Request a suggestion |
| `POST` | `/entries/audio` | Submit a voice entry (uploaded audio) |
| `POST` | `/entries/speech` | Synthesize a spoken reply |
| `GET` | `/events` | List the user's events (reminders) |
| `GET` / `POST` | `/friends` | List / add close friends |
| `DELETE` | `/friends/{id}` | Remove a friend |
| `GET` | `/counsellors` | Counsellor directory (demo data) |
| `GET` / `POST` | `/community/channels` | List channels / create one (3 per user per day) |
| `GET` / `POST` | `/community/channels/{id}/messages` | Read / post messages in a channel |
| `GET` / `PUT` | `/community/alias` | Your community alias / choose or change it |
| `GET` | `/community/alias/check?name=` | Is an alias available? |
| `GET` | `/community/members?q=` | Aliases for @mention autocomplete (HealAura included) |
| `POST` | `/community/images` | Upload an image (≤ 8 MB; deleted after 24 h) |
| `GET` | `/community/images/{id}` | Serve a shared image |
| `GET` | `/auth/languages` | Languages a person can choose |
| `PUT` | `/auth/profile` | Save name, language, interests |
| `POST` | `/auth/email/start`, `/auth/email/verify` | Add a verified email to an existing account |
| `GET` | `/friends/alerts` | Check-in emails sent, and when the next can go |
| `POST` | `/friends/test-alert` | Send a labelled test email to your close friends |
| `WS` | `/community/ws` | Live feed: send `{"type":"auth","token":…}` first, then `view` / `typing` |
| `GET` | `/entries/voices` | Voices for spoken replies and which are available |

## Building the frontend

```bash
cd frontend
npm run build     # type-checks and outputs to frontend/dist
npm run preview   # serve the production build locally
```

## Project layout

```
backend/          FastAPI app
  main.py         App entrypoint, lifespan, /health
  routes/         auth, entries, events, friends, community, support routers
  auth.py         Password hashing + bearer-token session dependency
  agent.py        Well-being agent: detects distress, alerts close friends
  email_client.py Gmail SMTP sender
  db.py           asyncpg pool, schema, per-user queries, email verification
  models.py       Pydantic request/response models
  classify.py     Sarvam classification / sentiment / NER
  sarvam_client.py  Sarvam API client (chat, STT, TTS)
  backchannel.py  Short listening/response generation
  scheduler.py    In-process reminder checks
frontend/         React + Vite client
  src/components/ Landing, Login, Signup, AppShell, BootScreen, Logo, Friends, Community, …
```

## Status

This is an early hackathon/demo build focused on the core reflection loop. Storage is standard backend Postgres and is **not yet privacy-hardened** — do not use real sensitive data.
