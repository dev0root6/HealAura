# HealAura

<p align="center">
  <img src="logo.png" alt="HealAura logo" width="200">
</p>

<p align="center">
  <strong>AI-assisted daily reflection for student well-being</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#getting-started">Getting Started</a> •
  <a href="#api">API</a> •
  <a href="#project-layout">Project Layout</a> •
  <a href="#research">Research</a>
</p>

---

HealAura is a web app that helps students manage stress through structured daily reflection. Write or speak a short entry — HealAura segments it into clauses, classifies each as a **memory**, **event**, or **task**, tags sentiment, and extracts dates, times, and people. Events become email reminders. Voice entries get spoken replies.

> **Note:** HealAura is a reflection aid, not a medical treatment.

## Features

### Talk with AI
The daily reflection journal. Choose **Short** replies (a few listening words) or **Conversation** mode (HealAura reflects on today's turns and asks a follow-up). **Live talk** is hands-free: speak naturally, and a 2-second pause sends; the reply is spoken back and HealAura listens again.

### Community
Discord-style channels (`#general`, `#exam-stress`, `#placements`, `#late-night`, `#small-wins`, `#vent`, plus user-created ones), all real-time over WebSocket: instant messages, typing indicators, presence counts, unread and @mention badges. Everyone picks a unique **community alias**. `@HealAura` asks the AI. **AI companions** (labelled as AI) offer supportive replies. Images can be shared (re-encoded, EXIF stripped). **Messages and images disappear after 24 hours.**

### Crisis Detection
Immediate safety net for self-harm language — in English, Tanglish, and Hinglish, including disguised spellings (`SU1c1de`, `s.u.i.c.i.d.e`, slang like "unalive"). Triggers a **crisis card** with helplines (Tele-MANAS 14416, toll-free 1-800-891-4416, emergency 112), and alerts close friends by email.

### Close Friends & Well-being Agent
Add people you trust. A background agent watches your recent reflections and, **only** when it detects sustained distress or a crisis, emails a check-in to you and nudges those friends. It never shares what you wrote.

### My Trends
Daily sentiment breakdown (stacked bars) and a smoothed "heaviness" line (EWMA, ~1 week memory). Range picker for 14/30/90 days, stat tiles, and an accessible table view.

### Daily Life Diary
HealAura writes the day as a first-person diary page — title, mood, highlights, coming up — in the language you wrote in. Updates as the day goes on; browse earlier days.

### Email Reminders
Events you mention ("interview tomorrow at 10") are emailed 1 hour before, or at 8 AM on the day if there's no time.

### Accounts & Profiles
Self-registration with email verification (6-digit code). Profile: preferred name, language (12 options including Tanglish/Hinglish), interests, and a verified email.

### Confidence & Active Learning
Each classification gets a confidence score via self-consistency (multiple concurrent LLM calls). Low-confidence segments are surfaced with "I'm not sure I read this one right — is it?" for user confirmation.

### Voice
7 Indian voices (Sarvam Bulbul) and 6 international voices (Groq Orpheus, English). Replies follow the language the person writes in.

## Architecture

- **Backend** — [FastAPI](https://fastapi.tiangolo.com/) (Python), served with Uvicorn. Persists to Neon (hosted Postgres) via `asyncpg`. Uses [Sarvam AI](https://www.sarvam.ai/) for classification, sentiment, NER (Sarvam-105B), speech-to-text (Saaras v3, handles code-mixed Tanglish/Hinglish), and text-to-speech (Bulbul v3). Background tasks (reminders, message expiry) run in-process via the scheduler.
- **Frontend** — React 19 + TypeScript, built with [Vite](https://vitejs.dev/). Talks to the backend through Vite's dev proxy.

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- A [Neon](https://neon.tech/) Postgres database (or any Postgres via `postgresql://`)
- A [Sarvam AI](https://www.sarvam.ai/) API key (see below)

### Getting a Sarvam AI API Key

HealAura uses [Sarvam AI](https://www.sarvam.ai/) for all NLP — text classification, sentiment analysis, named-entity recognition (Sarvam-105B), speech-to-text (Saaras v3), and text-to-speech (Bulbul v3). It handles code-mixed input (Tanglish, Hinglish) natively.

1. **Sign up** at [indus.sarvam.ai](https://indus.sarvam.ai/)
2. **Create an API key** at [Key Management](https://indus.sarvam.ai/key-management)
3. **Copy the key** into your `.env` file as `SARVAM_API_KEY`

**Pricing:** Pay-as-you-go with ₹100 in free credits on sign-up (no expiry). Example rates:

| Service | Model | Rate |
| --- | --- | --- |
| Text (chat/classify) | Sarvam-105B | ₹15 input / ₹60 output per 1M tokens |
| Speech-to-text | Saaras v3 | ₹0.49 per minute |
| Text-to-speech | Bulbul v3/v4 | ₹1.00 per 1,000 characters |

Prices in INR, exclude GST. Monitor usage and rate limits at [indus.sarvam.ai/billing](https://indus.sarvam.ai/billing).

**API details:**
- Base URL: `https://api.sarvam.ai`
- Auth header: `api-subscription-key: <YOUR_SARVAM_API_KEY>`
- Python SDK (optional): `pip install -U sarvamai`
- HealAura calls Sarvam directly via HTTP in `backend/sarvam_client.py` — no SDK needed.

**Rate limits:** Each entry makes 3–4 concurrent Sarvam calls (1 classification + 2 confidence samples + 1 back-channel). Free-tier rate limits may cause HTTP 429 on heavy use. Check limits at [indus.sarvam.ai/rate-limits](https://indus.sarvam.ai/rate-limits).

### Configuration

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
| `SARVAM_TTS_SPEAKER` | no | Fallback TTS voice (default `ishita`) |
| `SARVAM_TTS_LANGUAGE` | no | TTS language (default `en-IN`) |
| `SMTP_USER` | for email | Gmail address for sign-up codes and check-ins |
| `SMTP_PASSWORD` | for email | Gmail app password (needs 2FA) |
| `SMTP_HOST` / `SMTP_PORT` | no | Defaults `smtp.gmail.com` / `587` |
| `SMTP_FROM_NAME` | no | Sender display name (default `HealAura`) |
| `GROQ_API_KEY` | for companions | Groq key for community companions and Orpheus voice |
| `GROQ_CHAT_MODEL` | no | Companion model (default `openai/gpt-oss-20b`) |
| `COMMUNITY_COMPANIONS` | no | `0` disables companions (default on) |
| `CONFIDENCE_SAMPLES` | no | Extra classification samples per entry (default `2`; `0` disables) |
| `REMINDER_TIMEZONE` | no | Timezone for reminders (default `Asia/Kolkata`) |
| `NEON_FORCE_IPV4` | no | Force IPv4 for Neon connections on networks with broken IPv6 |

Without `SMTP_USER` / `SMTP_PASSWORD` the app runs fine — email features are skipped, and sign-up codes print to the backend log.

### Backend (port 8000)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd backend
uvicorn main:app --reload --port 8000
```

The database schema is created on first startup. Check `http://127.0.0.1:8000/health` to confirm.

### Frontend (port 5173)

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. The Vite dev server proxies API requests to the backend. Run the API as a single worker (the live community room is in-process).

## API

Interactive docs at `http://127.0.0.1:8000/docs` while the backend runs. All endpoints except `/health`, `/auth/login`, and `/auth/register/*` require `Authorization: Bearer <token>`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Health check |
| `POST` | `/auth/login` | Log in → bearer token |
| `POST` | `/auth/logout` | Invalidate token |
| `GET` | `/auth/me` | Current user |
| `POST` | `/auth/register/start` | Email verification code |
| `POST` | `/auth/register/verify` | Check code → sign-up token |
| `POST` | `/auth/register/complete` | Create account → bearer token |
| `GET` / `PUT` | `/auth/profile` | View / update profile |
| `GET` | `/auth/languages` | Available languages |
| `POST` | `/entries` | Submit text entry (`mode`: `short` or `long`) |
| `GET` | `/entries?date=` | List entries (optional date filter) |
| `PATCH` | `/entries/{id}` | Correct a classification |
| `GET` | `/entries/messages` | Conversation thread |
| `GET` | `/entries/day?date=` | Daily diary page |
| `GET` | `/entries/trends?days=` | Sentiment trends |
| `POST` | `/entries/audio` | Submit voice entry |
| `POST` | `/entries/speech` | Synthesize spoken reply |
| `GET` | `/entries/voices` | Available voices |
| `GET` | `/events` | List reminders |
| `GET` / `POST` | `/friends` | List / add close friends |
| `DELETE` | `/friends/{id}` | Remove a friend |
| `GET` | `/friends/alerts` | Check-in history |
| `POST` | `/friends/test-alert` | Send test email to friends |
| `GET` | `/counsellors` | Counsellor directory (demo) |
| `GET` / `POST` | `/community/channels` | List / create channels |
| `GET` / `POST` | `/community/channels/{id}/messages` | Channel messages |
| `GET` / `PUT` | `/community/alias` | Community alias |
| `GET` | `/community/members?q=` | @mention autocomplete |
| `POST` | `/community/images` | Upload image (≤ 8 MB) |
| `WS` | `/community/ws` | Real-time feed |

## Project Layout

```
backend/
  main.py              App entrypoint, lifespan, /health
  routes/              auth, entries, events, friends, community, support
  auth.py              Password hashing, bearer-token sessions
  agent.py             Well-being agent: detects distress, alerts friends
  safety.py            Crisis phrase detection (multi-language, anti-evasion)
  classify.py          Sarvam classification, sentiment, NER, confidence scoring
  sarvam_client.py     Sarvam API client (chat, STT, TTS)
  groq_client.py       Groq API client (companions, Orpheus voice)
  backchannel.py       Short/conversation response generation
  companions.py        AI community companions
  daily.py             Daily diary generation
  trends.py            Sentiment trends and heaviness scoring
  voice.py             Voice routing (Sarvam/Orpheus), voice picker
  db.py                asyncpg pool, schema, queries
  models.py            Pydantic request/response models
  email_client.py      SMTP sender
  emails.py            Email templates (sign-up, check-in, reminders)
  scheduler.py         In-process reminder and expiry checks
  send_setup_reminders.py  One-time setup reminder for older accounts
frontend/
  src/App.tsx          Main app component
  src/api.ts           API client
  src/main.tsx         Entry point
  src/index.css        Styles
research_paper/
  HealAura_IEEE_Paper.md   IEEE-format research paper
  eval/                    Benchmark evaluation scripts and results
  figures/                 Paper figures
```

## Research

The `research_paper/` directory contains an IEEE-format paper on HealAura's approach: LLM-based clause-level classification with self-consistency confidence scoring, a human-in-the-loop active learning cycle, and a well-being agent with tiered alert gates. Evaluation scripts benchmark against TF-IDF + Logistic Regression baselines on code-mixed (Tanglish) data.

## Status

Early hackathon/demo build focused on the core reflection loop. Storage is standard backend Postgres and is **not yet privacy-hardened** — do not use real sensitive data.

## License

This project is currently unlicensed. All rights reserved.
