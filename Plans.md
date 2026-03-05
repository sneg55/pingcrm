# Plans - Ping CRM

## Phase 1: Foundation (Weeks 1-4)

### 1.1 Project Scaffolding
- [x] `cc:完了` Initialize FastAPI backend project structure
- [x] `cc:完了` Initialize Next.js frontend project
- [x] `cc:完了` Set up PostgreSQL schema with Alembic migrations
- [x] `cc:完了` Configure environment variables and settings

### 1.2 Auth & Onboarding
- [x] `cc:完了` User auth (signup/login) with JWT
- [x] `cc:完了` Google OAuth integration for Gmail + Contacts
- [x] `cc:完了` Onboarding flow UI

### 1.3 Contact Management
- [x] `cc:完了` Contact model and CRUD API endpoints
- [x] `cc:完了` CSV import endpoint with field mapping
- [x] `cc:完了` Google Contacts one-way sync
- [x] `cc:完了` Manual contact creation UI
- [x] `cc:完了` Contact profile page with unified fields

### 1.4 Gmail Integration
- [x] `cc:完了` Gmail API thread sync service
- [x] `cc:完了` Interaction tracking from email threads
- [x] `cc:完了` Periodic sync job (Celery task)

### 1.5 Interaction Timeline
- [x] `cc:完了` Interaction model and API
- [x] `cc:完了` Timeline UI component (reverse chronological, grouped by platform)
- [x] `cc:完了` Manual note entry

### 1.6 Basic Relationship Scoring
- [x] `cc:完了` Scoring model implementation (signal-based points)
- [x] `cc:完了` Score display on contact cards (green/yellow/red)

## Phase 2: Intelligence (Weeks 5-8)

### 2.1 Telegram Integration
- [x] `cc:完了` MTProto client setup
- [x] `cc:完了` Chat history sync
- [x] `cc:完了` Contact matching from Telegram

### 2.2 Identity Resolution
- [x] `cc:完了` Tier 1: Deterministic matching (email, phone)
- [x] `cc:完了` Tier 4: User confirmation UI for low-confidence matches
- [x] `cc:完了` IdentityMatch model and merge logic

### 2.3 Context Detection Engine
- [x] `cc:完了` Twitter activity polling service
- [x] `cc:完了` LLM classifier for event detection (job change, fundraising, etc.)
- [x] `cc:完了` DetectedEvent model and storage

### 2.4 AI Message Composer
- [x] `cc:完了` Message generation service (Claude API)
- [x] `cc:完了` Tone and style adaptation from conversation history
- [x] `cc:完了` Draft editing UI

### 2.5 Follow-Up Engine
- [x] `cc:完了` FollowUpSuggestion model and generation logic
- [x] `cc:完了` Time-based + event-based triggers
- [x] `cc:完了` Weekly digest email (Celery scheduled task)

## Phase 3: Polish (Weeks 9-12)

### 3.1 Twitter Integration
- [x] `cc:完了` Twitter DM and mention sync
- [x] `cc:完了` Bio change monitoring

### 3.2 Dashboard
- [x] `cc:完了` "Reach out this week" section
- [x] `cc:完了` "Recent activity from your network" feed
- [x] `cc:完了` "Relationship health overview" summary
- [x] `cc:完了` "Recently contacted" list

### 3.3 Follow-Up Workflows
- [x] `cc:完了` Snooze, schedule, dismiss actions
- [x] `cc:完了` Notification system (in-app + email)

### 3.4 Identity Resolution v2
- [x] `cc:完了` Tier 2: Probabilistic matching (scored)

### 3.5 Performance & Hardening
- [x] `cc:完了` Optimize for 500+ contacts
- [x] `cc:完了` Error states and edge case handling
- [x] `cc:完了` Security audit (OAuth tokens, data access)
