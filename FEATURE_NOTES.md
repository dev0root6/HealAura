# HealAura — feature notes

Running notes on the feature roadmap: what was built, how it works, what's next, and what the
research paper will need once we update it. The paper (`research_paper/`) has **not** been changed
for any of this yet. See "Pending paper updates" at the bottom.

---

## Status at a glance

| # | Feature | Priority | Status |
|---|---|---|---|
| 1 | Instant crisis response | Must-fix | **Done** (2026-10-04) |
| 2 | Uncertainty-based "is this right?" prompts (active learning) | Research | **Done** (2026-10-04) |
| 3 | Mood trends dashboard | Research / product | **Done** (2026-10-04) |
| 4 | Request queue for Sarvam calls (rate limits) | Must-fix | Not started |
| 5 | Privacy hardening (encryption at rest, retention, export/delete) | Must-fix | Not started |
| 6 | Hybrid classifier (small supervised model + LLM fallback) | Research | Not started |
| 7 | Personal few-shot examples from user corrections | Research | Not started |
| 8 | Weekly reflection summary | Product | Not started |
| 9 | Smarter reminders (follow-up check-in after events) | Product | Not started |
| 10 | Tone of voice from speech (prosody / SER) | Research | Not started |
| 11 | Hinglish few-shot + more languages (Telugu, Kannada, Malayalam) | Product / research | Not started |
| 12 | Community moderation (LLM safety filter, report button) | Product / safety | Not started |
| 13 | Real counsellor booking + opt-in "share trend, not text" | Product | Not started |
| 14 | PWA / mobile app (push reminders, offline drafts) | Product | Not started |
| 15 | Consent & study mode (consent form, PSS-10/GAD-7, anonymised export) | Research | Not started |

---

## 1. Instant crisis response — done

**Problem.** An explicit self-harm or suicide message ("I want to end my life") was handled like
any other bad day: the support nudge said "counselling is coming soon", and friends were only
alerted after ≥ 3 negative segments in 24 h. That is too slow for a crisis.

**What it does now.**
- Each entry gets a `crisis` flag, set if **either**:
  - the back-channel LLM call returns `"crisis": true` (new field in the prompt, with a Tanglish
    crisis example), **or**
  - a deterministic phrase list matches (`backend/safety.py`: English, Tanglish and Hinglish
    phrasings such as "kill myself", "saaganum", "mar jaana", "khudkushi"). This safety net also
    covers the back-channel's fallback paths, where the model is down or its output can't be
    parsed and so reports no flags.
- `crisis` implies `needs_support`.
- The assistant turn is stored with `messages.crisis = true`, and the UI shows a **crisis card**
  right away: Tele-MANAS 14416, the Tele-MANAS toll-free 1-800-891-4416, and emergency 112
  (all tap-to-call), plus buttons that open Counsellors / Close friends.
- **Well-being agent:** a crisis skips gate G2 (sustained negativity), so trusted friends are
  alerted on the first crisis message. **G3 (12 h cooldown) and G4 (opt-in friend list) still
  apply.** The e-mail is still content-free.
- The non-crisis support nudge now links to the Counsellors tab instead of saying "coming soon".

**Files.** `backend/safety.py` (new), `backend/backchannel.py`, `backend/routes/entries.py`,
`backend/agent.py`, `backend/db.py` (new column `messages.crisis`, added by the startup
migration), `backend/models.py`, `frontend/src/components/CrisisCard.tsx` (new),
`Conversation.tsx`, `AppShell.tsx`, `api.ts`, `index.css`.

**Verified.**
- Live API: the Tanglish entry *"enakku saaganum pola iruku, ellam mudinjiduchu"* returned
  `crisis: true`, and the card rendered.
- Phrase net: "I want to die", "saaganum", "mar jaana chahta hoon" → match. "exam was killing me
  lol", "I could kill for biryani", "felt sad today" → no match.
- Agent: crisis with 0 negatives → alert. Crisis with no friends → none. Crisis inside the
  cooldown → none. Non-crisis with 0 negatives → none. The original 26 agent checks still pass.

**Open points / decide later.**
- **Verify helpline numbers before any real deployment.** They are hard-coded in
  `CrisisCard.tsx`. Consider making them configurable per institution (e.g., add the campus
  counselling line).
- Should a crisis bypass the 12 h cooldown too? Currently no, to avoid repeat e-mails, but this
  is a policy decision for the team / ethics review.
- The phrase list favours recall. Expect some false positives ("I want to die of embarrassment").
  It shows a helpline card, which is low-harm. Track how often it fires once real usage starts.
- The crisis friend e-mail uses the same wording as the normal alert. Maybe say "please check in
  soon"?

---

## 2. Uncertainty-based "is this right?" prompts — done

**Idea.** This is the active-learning query step from the base paper (Almadhor et al., IEEE
Access 2024). The model asks the user to confirm only the segments it is unsure about, instead of
every segment or none.

**How confidence is computed (self-consistency).**
- Along with the normal classification, `CONFIDENCE_SAMPLES` extra classifications (default **2**)
  run **concurrently** at temperature 0.7.
- Each stored segment is matched to the most-overlapping segment in each extra sample (word
  Jaccard). Confidence = share of runs (main + successful samples) that agree on **both** type and
  sentiment. With 2 samples the possible values are 1.0, 0.67 and 0.33.
- Stored in the existing `entries.ai_confidence` column, which was unused until now.
- The extra samples can never fail an entry. If they error out, confidence just stays `null`, and
  fallback (unclassified) entries get no confidence.
- `CONFIDENCE_SAMPLES=0` turns it off.

**UI.** A segment is "unsure" when `ai_confidence < 0.75` and the user hasn't confirmed or
corrected it. Unsure cards get a dashed border and the line *"I'm not sure I read this one right —
is it?"*. The "What I picked up" panel opens automatically and shows "· N to check".

**Files.** `backend/classify.py` (`classify_with_confidence`, `score_confidence`,
`_sample_once`), `backend/routes/entries.py`, `frontend/src/components/EntryCard.tsx`
(`isUnsure`), `Conversation.tsx`, `index.css`, `.env.example`, `README.md`.

**Verified.** In a live run of 3 Tanglish entries, all segments scored 1.0 except one, which
scored 0.67 and got the prompt in the UI. A unit check of `score_confidence` with merged and split
sample segments gave the expected values.

**Costs / caveats.**
- **Each entry now makes 1 + 2 = 3 classification calls (plus the back-channel call).** They run
  in parallel, so latency barely changes, but API usage and HTTP 429 risk roughly triple. Feature
  #4 (request queue) matters more now.
- The research benchmark (`research_paper/eval/run_llm_eval.py`) calls `classify_entry` directly,
  so its results are unaffected.
- The 0.75 threshold is a first guess. Tune it once correction data exists (see "Pending paper
  updates").

---

## 3. Mood trends dashboard — done

**What it shows** (new **My trends** tab):
- A range picker: 14 / 30 / 90 days.
- Stat tiles: days you wrote; share of moments that were heavy (negative); current "heaviness"
  with ▲/▼ vs last week (shown only for a change of ≥ 5 points).
- **What each day held:** a stacked bar per day (positive / neutral / mixed / negative), with a
  legend and a hover/tap tooltip per day.
- **Heaviness over time:** an EWMA (α = 0.3, about a one-week memory) of each day's negative
  share. Days with no entries carry the last value forward, because not writing is not the same
  as feeling fine.
- A **Show as a table** view, so nothing depends on colour alone.

**Backend.** `GET /entries/trends?days=N` (7–180). Counts use the **effective** label
(`COALESCE(corrected_sentiment, sentiment)`), the same rule the well-being agent uses, so user
corrections flow into the trends. Logic is in `backend/trends.py` (`summarise` is pure and
unit-testable); the query is `db.sentiment_counts_by_day`.

**Design notes.**
- The palette was checked with the dataviz validator: green / gray / purple / red. Gray is a
  deliberate neutral midpoint. CVD separation is in the 6–8 band, so secondary encoding is
  required, and we have it: 2 px gaps between stacked segments, a legend, tooltips and the table.
- Charts measure their container width (ResizeObserver), so axis text stays readable on phones.
  Tested at 1100 px and 390 px with no horizontal scroll.
- The wording avoids clinical terms ("heaviness", "a look back, not a diagnosis").

**Files.** `backend/trends.py` (new), `backend/db.py`, `backend/models.py` (`DayTrend`,
`TrendsOut`), `backend/routes/entries.py`, `frontend/src/components/Trends.tsx` (new), `api.ts`,
`AppShell.tsx` (new tab, plus `aria-label` on tabs so icon-only mobile tabs have names),
`index.css`.

**Ideas for later.** Per-topic trends (exams, placements, family) from segment text; mark days with
a crisis flag; weekly e-mail digest (ties into #8).

---

## Next up (suggested order)

1. **#4 Request queue.** Needed more now that each entry makes 3–4 LLM calls. Options: an
   in-process `asyncio.Semaphore` plus retry/backoff on 429 in `sarvam_client`, then a real job
   queue if multi-user load grows.
2. **#5 Privacy hardening.** Encrypt `raw_text` / `segment_text`, set a retention policy, add
   "export my data" and "delete my account" endpoints. Required before the user study (#15).
3. **#6 Hybrid classifier.** The benchmark showed TF-IDF + LR (0.417 macro-F1) beating the LLM
   (0.342) on Tanglish comments. The `ai_confidence` from #2 could decide when to defer to which
   model.
4. **#15 Study mode.** Needed to fill the paper's pending tables (RQ1, RQ3–RQ6).

Other ideas from the brainstorm are kept in the table above.

---

## Pending paper updates (do NOT apply until we decide to update the paper)

- **Section III-C / III-F:** describe the `crisis` flag (LLM + phrase safety net), the crisis
  card, and the G2 bypass for crises (G3/G4 kept). Update Fig. 4 (agent gates) and the formal
  alert condition: alert ⇔ (σ ∧ N_W ≥ k ∨ crisis) ∧ cooldown ∧ friends.
- **Section III-E:** `ai_confidence` is now implemented by self-consistency (2 extra samples at
  T = 0.7, Jaccard segment matching), and low-confidence segments are surfaced for confirmation.
  This moves "uncertainty-driven confirmation" out of Future Work and into the system design, and
  makes the active-learning link to the base paper [7] concrete. Update Fig. 3(b).
- **New subsection (System design or Implementation):** the mood trends dashboard, its EWMA
  heaviness score (α = 0.3, carry-forward), and corrections flowing into trends.
- **Section V-D (reliability):** note that per-entry API calls rose from 2 to 4 (1 classify + 2
  confidence samples + 1 back-channel), which matters given the measured 429 rate limits.
- **Possible new experiments:**
  - **Confidence calibration:** on the 500-comment benchmark, do low-confidence items have lower
    accuracy? (Reliability diagram / AUROC of confidence vs. correctness.) This would directly
    support the active-learning claim.
  - **Crisis detector:** precision/recall of the phrase net + LLM flag on a small labelled set
    (needs careful, ethics-reviewed data).
- **Section VI-C (future work):** remove items now done (uncertainty-driven confirmation, partly
  trend modelling); keep the rest.
- **Table III (implementation):** add `safety.py`, `trends.py`, and the `CONFIDENCE_SAMPLES` config.

---

## Round 2 (2026-10-04): voice, fonts, companions, sign-up, icons, logo

**1. Warmer voice.** `backend/voice.py` routes each spoken reply:
- English replies → Groq **Orpheus** (expressive, with a `[warm]` / `[softly]` direction).
  **Blocked until the Groq org accepts the Orpheus terms:** https://console.groq.com/playground?model=canopylabs%2Forpheus-v1-english.
  Until then it falls back to Sarvam automatically, and retries every 10 minutes.
- Everything else (and the fallback) → Sarvam Bulbul v3 with the user's chosen voice (Ishita by default;
  Kavya, Priya, Shubh, Rohan) at pace 0.92, or 0.85 on heavy replies.
- The voice picker appears in the header when voice is on and is saved per browser.
- **Fonts:** Fraunces (headings) + Plus Jakarta Sans (body), from Google Fonts.

**2. Community companions** (`backend/companions.py`, Groq `openai/gpt-oss-20b`): 1–2 persona replies
12–45 s after a human post. They're labelled **AI** in the UI, never reply to each other, are capped at 12
per 10 min, and send a crisis post one careful helpline reply. People can't post under a companion handle.
- Prompt rules: reply in the post's language mix; no invented personal experiences.
- Decision: they are labelled as AI on purpose. Unlabelled bots in a mental-health peer space would be
  deceptive. Removing the label is one line in `Community.tsx` if the team decides otherwise.

**3/5. Self-registration + email verification** (`backend/routes/auth.py`): email → 6-digit code
(10 min, 5 tries, resend after 60 s) → sign-up token (30 min) → username (3–32 chars) + password (≥ 8 chars).
- Sign in with a username or an email. The admin panel, the admin endpoints and the `admin/admin` seed are removed.
- Existing `admin`/`demo` rows are still in the DB. Delete them or change their passwords.
- Email from HealAura (`backend/emails.py`, HTML + text): sign-up code, friend check-in (urgent
  wording on crisis), and a new **self check-in to the user** with helplines that says whether friends
  were nudged.
- Tested: SMTP login OK, all 4 templates delivered to HealAura's own inbox, and a real sign-up code was sent.

**4. Icons.** All emoji are replaced with lucide-react icons (tabs, counsellor Call/Email, tags, mic, voice).

**Logo + loading screen.**
- Files: `logo.png` (1024 px, repo root and `frontend/public`), `frontend/public/logo.svg` (favicon),
  `apple-touch-icon.png`.
- `Logo.tsx` in the header, landing and auth screens.
- `BootScreen.tsx` animation: drifting aurora blobs, ripples, orbiting sparks, a beating heart with a
  self-drawing pulse, a letter-by-letter wordmark, and "breathe in / breathe out".
- Timing: 2.6 s on the first visit per session, 0.7 s after that, then a blur-out exit. It holds still
  under reduced-motion.

**Pending paper updates (add to the list above):** companions in Section III-G; the email-verified
accounts replacing admin provisioning; the user self check-in in the agent (Section III-F); and the voice
routing in Section III-D.

---

## Round 3 (2026-10-04): tunnel, more voices, real-time channels

- **Vite:** `server.allowedHosts: ['.trycloudflare.com']`, plus `ws: true` on the `/community` proxy.
- **Voices** (`backend/voice.py`, `GET /entries/voices`):
  - 7 Indian voices (Sarvam, all languages): Ishita, Kavya, Priya, Simran, Shubh, Rohan, Kabir.
  - 6 international voices (Groq Orpheus, English): Hannah, Diana, Autumn, Daniel, Austin, Troy.
  - The international voices show "not enabled yet" until the Groq org accepts the Orpheus terms
    (https://console.groq.com/playground?model=canopylabs%2Forpheus-v1-english). Non-English replies
    in an international voice use a gender-matched Sarvam voice. Long replies are split into ≤ 188-char
    pieces and the audio joined.
- **Community = real-time Discord-style channels:**
  - `community_channels` table with 6 default channels; any user can create up to 3 per day.
  - Messages carry `channel_id`; old messages were moved to `#general`.
  - One WebSocket per tab (`/community/ws`); the token goes in the first frame, never in the URL.
    Live messages, new channels, per-channel presence, typing hints, and unread badges in the client.
    Falls back to polling if the socket drops, and reconnects with backoff.
  - Handles are stable per person per day (hash of user + date), so two people can follow a
    conversation. They're not linked to the account in the API.
  - Companions stay quiet when another person posted in the channel in the last 5 minutes (a live
    conversation), except that a crisis post always gets the helpline reply.
  - Limitation: the room lives in process memory, so run one API worker. Scaling out needs
    Redis pub/sub or similar.
- **Bug fixed:** a stale socket's late `onclose` (from React StrictMode's double mount) cleared the
  live socket reference, so view/typing frames were silently dropped.
- **Tested:** two browsers as two users, checking presence, typing, both directions of live
  messages, unread badge, and live channel creation; desktop and 390 px mobile. Test data deleted.
- **Note:** Neon queries take about 3 s from this machine, so first loads feel slow. Consider a
  region closer to the server, or caching the channel list.
