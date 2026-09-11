# PLAN.md

## Project
Working name: **[TBD]** — AI-assisted daily reflection webapp for reducing stress impact/source (not a cure).

## Current Decision
- **Platform: Web app** (not Flutter/mobile) for now. Revisit mobile later if needed.
- **Database: Neon (Postgres)** — hosted, supports remote demo access and concurrent dev access across teammates
- Conversational AI: Sarvam (opt-in, secondary feature)
- Sentiment/classification/NER: Sarvam-105B via Chat Completions (prompt-based, not a dedicated endpoint)
- STT: Sarvam Saaras v3 (handles code-mixed Tanglish/Hinglish)
- Background jobs (reminders/alerts): FastAPI `BackgroundTasks` + APScheduler — no external queue infra (no Celery/Redis) for this scope

## Goal for This Phase
Get a working end-to-end demo of the **core loop**:
1. User submits a daily entry (text first, voice later)
2. Entry is segmented into clauses/sentences
3. Each segment classified: memory / event / task, with sentiment + extracted date/time/person
4. Structured entries stored, displayed back to user
5. User can confirm/correct classification (1-tap)
6. Events with a date/time create a reminder (visible in-app; browser notification optional)

Everything else (voice input, alert-to-contact flow, conversational AI, on-device/local encryption, mood trend charts) comes **after** this loop works reliably.

## Scope for v1 (Hackathon/Demo Build)

### In scope
- Web app, text input first (voice input as stretch goal if time allows)
- Sarvam-105B for segmentation + classification + sentiment + NER (single prompt call per entry)
- Structured storage on Neon (Postgres)
- Basic dashboard: today's entries, classified and tagged, with a confirm/edit control
- Manual "create reminder" from an extracted event (does not need to be a full notification system yet)
- Scheduled reminder check (APScheduler, in-process) — polls for due events, triggers in-app/browser notification

### Explicitly out of scope for v1
- Mobile app (Flutter) — deferred
- On-device/local encrypted storage — deferred, use normal backend storage for now, flag it clearly as not-yet-privacy-hardened
- Voice-based stress/emotion detection — deferred
- Contact-alert feature with verification flow — deferred (demo/mock only if needed for pitch)
- Multi-day mood trend analytics — stretch goal, not core
- Conversational AI companion — stretch goal, build only if core loop is solid with time to spare

## Milestones

| # | Milestone | Deliverable |
|---|-----------|-------------|
| 1 | Sarvam API wired up | Single working call: text in → structured JSON out |
| 2 | Segmentation logic | One entry with multiple sentiments/types returns multiple structured entries |
| 3 | Storage + retrieval | Entries persisted, retrievable by date |
| 4 | Minimal frontend | Text box to submit entry, list view of today's classified entries |
| 5 | Confirm/correct UI | User can tap to fix a wrong classification |
| 6 | Event → reminder | Extracted event with date/time shown as a reminder card |
| 7 | Background scheduler | APScheduler job checks for due events, fires notification/alert |
| 8 | (Stretch) Voice input | Sarvam STT wired into the same pipeline |
| 9 | (Stretch) Trend view | Simple chart of sentiment over recorded days |
| 10 | (Stretch) Conversational AI | Opt-in chat screen using Sarvam conversational endpoint |

## Open Questions / Decide Later
- Auth: none for demo, or simple single-user session?
- Hosting: local for demo, or deploy (Render/Railway/Vercel) if live demo needed?
- Do we mock the contact-alert flow for the pitch, or skip mentioning it as "built" and present as roadmap only?
- Reminder delivery: in-app list only vs. actual browser push notifications — decide based on time left.

## Notes
- Privacy pitch (local storage, zero cloud retention) is currently **aspirational for v1** — the web app stores data on Neon (hosted Postgres), not on-device. Do not claim on-device storage in the pitch until this is actually implemented; present it as designed/roadmapped, not shipped.
- Segmentation-before-classification (see implementation.md) is the most technically novel part of this build — prioritize getting this right over polish elsewhere.
- Alerts/reminders run via an in-process scheduler (APScheduler), not a separate task-queue service — keep it that way unless a real scaling need appears.
