# Plan Critic Memory — Ping CRM

## Project Architecture (verified 2026-03-04)
- Backend: FastAPI + SQLAlchemy async + Celery/Redis
- Frontend: Next.js 14 (App Router) + React Query + Tailwind
- DB models: Contact, Interaction, DetectedEvent, FollowUpSuggestion, IdentityMatch, User, Notification

## Key Verified Gaps Found (spec drift audit)

### Scoring model mismatch (critical)
- Spec (4.6): +5 per message last 30d, +3 reply <48h, +2 intro, +2 mutual, -2/month silence
- Implementation (scoring.py): +2 per interaction last 30d, +1 per interaction last 90d, capped at 10
- No silence penalty, no reply-time signal, no intro/referral signal

### Weekly digest is not actually sent (functional gap)
- digest_email.py explicitly logs instead of SMTP: "MVP: log instead of sending via SMTP (Phase 3)"
- Plans.md marks this as complete; spec 4.7 calls for email delivery

### Telegram verify flow broken in frontend (critical bug)
- Backend /auth/telegram/verify requires phone_code_hash in request body
- Frontend settings/page.tsx never captures phone_code_hash from connect response
- Sends only {phone, code} — verify will always fail (422)

### Twitter DM contact matching is incorrect (functional gap)
- sync_twitter_dms assigns DMs to the first contact with any twitter_handle, not the actual sender
- This means DM interactions will be linked to wrong contacts

### Dashboard "Recent activity from your network" section missing
- Spec 4.9 requires a feed of detected events from contacts
- Dashboard page only has: reach out suggestions, recently contacted, relationship health
- No DetectedEvent feed implemented anywhere in frontend

### Bio change detection stored in contact.notes (design smell)
- Twitter bio stored with sentinel prefix "__twitter_bio__:" in notes field
- Pollutes user-visible notes; no dedicated column

### Notification system not wired to suggestion generation
- services/notifications.py exists but notify_new_suggestions is never called from tasks.py or followup_engine.py

### CSV import missing twitter/telegram fields
- Spec 4.1: CSV optional fields include twitter, telegram
- contacts.py import loop does not map twitter_handle or telegram_username from CSV rows

### Onboarding only covers Google — no Telegram/Twitter setup in onboarding
- Spec 3 (core user flow): "connect Gmail, Telegram, and/or Twitter" at step 1
- Onboarding page has 4 steps; step 2 only shows Google connect

## Confirmed Working
- All 5 core DB models match spec exactly
- Tier 1 deterministic + Tier 2 probabilistic + Tier 4 user-confirmation identity resolution all implemented
- Celery beat schedule covers Gmail (6h), Telegram (12h), Twitter (12h), digest (Monday 9am), scoring (daily 2am)
- All three follow-up trigger types (time-based, event-based, scheduled) implemented
- LLM classifier (Claude) for tweet + bio classification implemented
- AI message composer with tone analysis implemented
- Snooze/dismiss/schedule/send all implemented end-to-end
- Contact profile page shows twitter_handle and telegram_username fields
- PKCE store for Twitter OAuth is in-memory (not Redis) — production risk but functional for MVP
