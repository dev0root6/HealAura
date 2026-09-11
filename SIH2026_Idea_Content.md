# SIH 2026 — Idea Submission Content

*Fill in before submitting: Problem Statement ID, Theme, Team ID, Team Name (registered on portal).*
*PS Category: Software*

---

## Slide 1 — Title Page
- Problem Statement ID – **[fill in]**
- Problem Statement Title – **[fill in — match to the SIH PS you're applying under, e.g. mental wellness / stress management for students]**
- Theme – **[fill in, e.g. MedTech / BioTech / HealthTech]**
- PS Category – Software
- Team ID – **[fill in]**
- Team Name – **[fill in]**

---

## Slide 2 — Idea Title: [Working name, e.g. "SAKHI" / "MindLog" / your pick]

### Proposed Solution
- AI-assisted daily reflection app that reduces the *impact and source* of stress, not a cure — captures 2 minutes of daily voice/text about the user's day
- Silently classifies each spoken/written moment into three buckets: **Memory**, **Event/Reminder**, **Emotion signal** — no default chatbot response
- Auto-creates reminders/alerts from casually mentioned events ("tomorrow I have a meeting with X at 3pm")
- Tracks emotional trend privately over time; user confirms/corrects AI's read in one tap (human-in-the-loop, not black-box scoring)
- If negative-emotion pattern persists, **verifies with the user first**, then (only if configured) alerts a trusted contact — designed to push toward real human connection, not AI dependency
- Optional, opt-in conversational AI for private venting — deliberately secondary, not the core interaction

### How it Addresses the Problem
- Most journaling/wellness apps lead with an AI chatbot companion, increasing AI-dependency instead of reducing it
- Nothing in the market extracts actionable events from natural, casual, code-mixed speech and turns them into reminders
- Alerting mechanisms elsewhere are automatic/opaque; this design requires self-verification before any third party is notified — cutting false-positive harm

### Innovation & Uniqueness
- Silent classification-first architecture (memory / event / emotion) with zero default AI conversation
- Sentence/clause-level segmentation before classification — a single 2-min entry can yield multiple structured entries (e.g. one task, one event, one memory) instead of one blanket label
- Built for real Indian speech patterns: code-mixed Tanglish/Hinglish, not just clean English input
- Verified human-escalation model instead of AI-as-companion
- Local, encrypted on-device storage; cloud LLM used only per-session for processing (zero data retention), not for storing user history

---

## Slide 3 — Technical Approach

### Technologies
- Platform: Web app (React frontend + FastAPI backend)
- Speech-to-Text: **Sarvam Saaras v3** — handles code-mixed and regional Indian speech (Tanglish/Hinglish) natively, not adapted from an English-first model
- Classification + NER + sentiment: **Sarvam-105B** (Chat Completions API) — single structured prompt per segment, returns type (memory/event/task), sentiment, and extracted date/time/person as JSON
- Conversational AI (optional, opt-in feature): **Sarvam** conversational/chat endpoint
- Database: **Neon (hosted Postgres)**
- Background jobs: FastAPI `BackgroundTasks` (async processing) + **APScheduler** for scheduled reminder/alert checks — lightweight, in-process, no separate queue infra
- Notifications: in-app reminder list; browser notifications as stretch goal

### Methodology / Flow
1. User submits ~2 min daily entry (text now, voice as stretch goal)
2. Sarvam STT (Saaras v3) → transcript, when voice is used
3. Transcript **segmented by sentence/clause** (not treated as one blob) — a single entry can contain multiple distinct moments
4. Each segment sent to Sarvam-105B with a structured prompt → classified as Memory / Event / Task, with sentiment (positive/negative/neutral/mixed) and extracted date/time/person
5. Structured entries stored in Neon (Postgres)
6. Segments with a date/time → reminder created; a scheduler job (APScheduler) checks due events and triggers an in-app alert
7. Emotion trend updated per segment → user shown daily summary → confirms/corrects AI's read (1-tap)
8. If negative pattern persists → in-app check-in with user → only on confirmation, optional alert to pre-approved contact (roadmap item, not yet built)
9. Optional: user taps "Talk to someone" → opt-in Sarvam-powered conversational session

*(Flowchart to be inserted here in final PPT)*

---

## Slide 4 — Feasibility & Viability

### Feasibility
- All components (STT, LLM classification/NER, local encrypted storage) use existing, proven technology — no novel research required
- Cloud-LLM-with-local-context pattern is a known architecture (similar to OpenRouter-style API usage)

### Challenges & Risks
- Classifying emotion/sentiment reliably from casual, code-mixed (Tanglish/Hinglish), sarcastic speech — e.g. distinguishing a neutral fact ("I ate biryani") from an opinion-bearing statement ("I ate biryani, it was great")
- A single entry can mix multiple moments with different emotional tones — naive whole-entry tagging loses this nuance
- Cold-start problem: no per-user baseline on day 1, so early stress trends are less reliable
- False positives/negatives in the alert feature carry real emotional and trust consequences
- On-device encrypted storage + biometric key management adds engineering overhead

### Mitigation Strategies
- Sentence/clause-level segmentation before classification, so mixed entries (e.g. "proud of my project but felt it was incomplete, meeting my GF tomorrow") produce separate, correctly-tagged entries instead of one blended label
- Sarvam-105B is trained on Indian languages and code-mixed text specifically, reducing misfires vs. a generic English-first model on Tanglish/Hinglish input
- Few-shot prompt examples covering evaluative-language vs. neutral-fact pairs, to stop the model defaulting to positive sentiment purely from pleasant topics
- Treat AI's emotional read as a *suggestion*, always confirmed/corrected by user (1-tap) — builds a personal labeled dataset over time to improve accuracy
- Mandatory self-verification step before any contact alert is sent — no silent automatic alerts
- Start with coarse valence (positive/negative/neutral) + trend detection relative to user's own baseline, not absolute "stress scores"
- Zero-retention agreement with LLM provider; no raw audio retained post-transcription

---

## Slide 5 — Impact & Benefits

### Target Audience
- Students and young professionals facing academic/work-related stress, exam pressure, relationship and social stress
- Anyone wanting a low-friction way to track emotional wellbeing without committing to therapy-app-style engagement

### Benefits
- **Social:** Encourages real human support networks instead of AI-dependency; reduces stigma via private, judgment-free daily reflection
- **Economic:** Free/low-cost preventive tool; reduces downstream burden on institutional counselling resources by surfacing patterns early
- **Personal productivity:** Automatic event/reminder capture from natural speech reduces missed commitments
- **Privacy-first:** On-device storage builds trust, especially relevant to India's growing data-privacy awareness

---

## Slide 6 — Research & References
- WHO factsheet on stress and mental health interventions — [who.int]
- Existing journaling/mood-AI apps reviewed for gap analysis: Day One (Journal AI), Diarly, Pensio, Reflectr, Diarium, Deariary
- Sarvam AI API docs — Saaras v3 (Speech-to-Text), Sarvam-105B (Chat Completions), built for Indian languages and code-mixed speech — docs.sarvam.ai
- Sarvam call-analytics cookbook (STT + diarization + LLM sentiment analysis pipeline) — reference architecture for this project's classification pipeline
- Zero-data-retention API policies (LLM provider enterprise API docs)
- CBT/ACT literature on temporal anchoring and pronoun-shift markers in journaling text (used for emotion-signal design rationale)
- *(Add your own dataset/paper links here before submission)*
