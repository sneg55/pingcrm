# Ping: AI Networking CRM, MVP Product Spec

**Version:** 0.1 (MVP)
**Last updated:** March 4, 2026

---

## 1. What This Is

Ping is a personal networking CRM that helps people maintain professional relationships without the manual work. Users import their contacts, connect their email and messaging accounts, and Ping watches for relevant activity across platforms. When something worth acting on happens, like a contact changing jobs or going quiet for months, Ping suggests a follow-up with a draft message ready to send.

The MVP focuses on three platforms: **Email (Gmail), Telegram, and Twitter (X)**. LinkedIn is excluded due to API restrictions.

**One-line pitch:** Upload your contacts, connect your accounts. Ping tells you who to reach out to and writes the message.

---

## 2. Target Users

The MVP is built for people who have large professional networks and whose relationships directly affect their income or deal flow.

**Primary audience:**
- Startup founders networking with investors, partners, and hires
- Venture investors maintaining relationships with portfolio founders and co-investors
- Recruiters managing candidate and client pipelines
- Sales professionals tracking prospects and warm leads

**Secondary audience:**
- Freelancers and consultants sourcing new work through referrals
- Job seekers staying top-of-mind with hiring managers

**Common traits:** These users already use Twitter and Telegram heavily for professional communication, have 200+ professional contacts they care about, and lose track of people they intend to stay in touch with.

---

## 3. Core User Flow

The MVP has one core loop:

```
Connect accounts → Import contacts → System monitors activity
→ Weekly digest of people to reach out to → One-click AI message → Send
```

**Step-by-step:**

1. User signs up and connects Gmail, Telegram, and/or Twitter.
2. User imports contacts via CSV, Google Contacts sync, or manual entry.
3. Ping builds unified profiles by matching identities across platforms.
4. Ping ingests interaction history and begins tracking public activity.
5. Each week, Ping delivers a digest: "Here are 3-5 people worth reaching out to, and why."
6. For each suggestion, Ping provides an AI-drafted message. User can edit, send, schedule, or dismiss.

---

## 4. Feature Spec

### 4.1 Contact Import & Profile Creation

**What it does:** Gets contacts into the system and creates a single profile per person.

**Import methods (MVP):**

| Method | Details |
|--------|---------|
| CSV upload | Minimum fields: `name, email`. Optional: `twitter, telegram, company, notes` |
| Google Contacts sync | OAuth connection, one-way import. Pulls name, email, phone, company, title, notes |
| Manual entry | Add contacts one at a time through the UI |

**Unified contact profile fields:**

| Field | Source |
|-------|--------|
| Full name | CSV / Google / manual |
| Email(s) | CSV / Google / Gmail sync |
| Twitter handle | CSV / manual / bio matching |
| Telegram username | CSV / manual / Telegram sync |
| Company | CSV / Google / Twitter bio / email domain |
| Title/role | CSV / Google / Twitter bio |
| Tags | User-assigned |
| Notes | User-entered free text |
| Relationship strength score | System-calculated |
| Last interaction date | System-tracked |
| Source | How they were imported |

**User story:** "I upload a CSV of 300 contacts from a conference. Ping creates profiles and starts matching them to Twitter handles and Telegram usernames I already have connected."

---

### 4.2 Identity Resolution

**What it does:** Figures out that alex@startup.com, @alexbuilds on Twitter, and @alexr on Telegram are all the same person.

**Matching tiers:**

**Tier 1, Deterministic (auto-merge):**
- Same email address appears in multiple sources
- Telegram contact shares the same phone number as a Google contact
- Twitter bio contains an email that matches an existing contact

**Tier 2, Probabilistic (scored, auto-merge above 85%):**

```
match_score =
  0.40 × email_match +
  0.20 × name_similarity +
  0.20 × company_match +
  0.10 × username_similarity +
  0.10 × mutual_signals
```

**Tier 3, AI-assisted (for edge cases):**
- LLM compares two profile summaries and returns a probability
- Example: LinkedIn-style bio vs. Twitter bio, "Likely same person: 92%"

**Tier 4, User confirmation (below 70% confidence):**
- System surfaces a card: "Are these the same person?" with both profiles shown side by side
- User confirms or dismisses. System learns from corrections.

**MVP scope:** Tier 1 and Tier 4 are required. Tier 2 is strongly recommended. Tier 3 can ship in a fast-follow.

---

### 4.3 Platform Integrations

#### 4.3.1 Email (Gmail)

**Integration method:** Gmail API via OAuth

**What Ping reads:**
- Email threads (sender, recipient, subject, timestamps, body snippets)
- Contact metadata

**What Ping tracks:**
- Last email exchanged with each contact
- Email frequency and response times
- Meeting invitations (as interaction signals)

**What Ping does NOT do (MVP):**
- Send emails on behalf of the user (drafts only)
- Read email body content for AI training beyond context extraction

---

#### 4.3.2 Telegram

**Integration method:** Telegram user client via MTProto (not bot API)

**Why MTProto:** The bot API only accesses conversations with the bot itself. MTProto gives access to the user's actual chat history, which is where the real relationship data lives.

**What Ping reads:**
- Chat history (DMs and group messages)
- Contact list
- Last message timestamps

**What Ping tracks:**
- Last conversation with each contact
- Message frequency
- Active group memberships (as shared-context signals)

**What Ping does NOT do (MVP):**
- Send Telegram messages automatically
- Monitor channels or bots

---

#### 4.3.3 Twitter (X)

**Integration method:** X API v2 via OAuth

**What Ping reads:**
- DMs
- Mentions and replies
- User tweets (for contacts in the system)
- Bio changes

**What Ping tracks:**
- Last DM or reply with each contact
- Public tweets from contacts (for context detection)
- Bio updates (job changes, milestones)

**What Ping does NOT do (MVP):**
- Import the full following list (requires Enterprise tier, too expensive)
- Post tweets or send DMs automatically

**Contact discovery without the following list:** Ping builds the Twitter contact graph from activity. People you DM, people who mention you, people you reply to. For most users, this captures the contacts that actually matter.

---

### 4.4 Interaction Timeline

**What it does:** Shows every touchpoint with a contact in a single, chronological feed.

**Example timeline for "Alex Rivera":**

```
Mar 3, 2026  | Telegram DM: "Let's catch up after the conference."
Jan 12, 2026 | Twitter DM: "Loved your thread on agents."
Oct 4, 2025  | Email: Intro to investor (cc'd)
Aug 15, 2025 | Telegram: Shared article about seed fundraising
```

**Interactions captured:**
- Emails sent/received
- Telegram messages (DMs)
- Twitter DMs, mentions, replies
- User-added notes (manual entries)

**Display rules:**
- Reverse chronological (newest first)
- Grouped by platform with icons
- Truncated previews, click to expand
- "Add note" button always visible at top

---

### 4.5 Context Detection Engine

**What it does:** Monitors public activity from contacts and classifies events that are worth acting on.

**Event types detected:**

| Event | Signal Source | Example |
|-------|-------------|---------|
| Job change | Twitter bio update, tweet | "Excited to join Stripe" |
| Fundraising | Tweet, email mention | "We just closed our seed round" |
| Product launch | Tweet | "We shipped today" |
| Promotion | Twitter bio, tweet | New title in bio |
| Personal milestone | Tweet | Wedding, move, new baby |
| Conference/event | Tweet, email | Speaking at or attending an event |

**How it works:**
1. Activity collector polls Twitter every 6-24 hours for each tracked contact.
2. New tweets and bio changes are run through an LLM classifier.
3. Classifier outputs: `{event_type, confidence, summary}`.
4. Events above confidence threshold are stored and linked to the contact profile.
5. High-priority events trigger follow-up suggestions.

**MVP scope:** Twitter activity only. Email-based event detection (parsing email content for milestones) is a Phase 2 feature.

---

### 4.6 Relationship Strength Scoring

**What it does:** Assigns each contact a numeric score reflecting how active and healthy the relationship is. Used to prioritize follow-up suggestions.

**Scoring model (v1, simple):**

| Signal | Points |
|--------|--------|
| Message exchanged in last 30 days | +5 |
| Reply within 48 hours | +3 |
| Introduction or referral made | +2 |
| Mutual interaction (both sides initiate) | +2 |
| Per month of silence | -2 |

**Score interpretation:**
- 8+ = Active relationship, no follow-up needed
- 4-7 = Warm, could use a check-in soon
- 1-3 = Cooling off, follow-up recommended
- 0 or below = At risk of going cold

**Display:** Simple color indicator on the contact card (green / yellow / red).

---

### 4.7 Smart Follow-Up Engine

**What it does:** Generates a weekly list of contacts worth reaching out to, ranked by a combination of relationship score, detected events, and time since last interaction.

**Follow-up triggers:**

| Trigger Type | Rule | Example |
|-------------|------|---------|
| Time-based | No interaction in 90+ days, score < 4 | "You haven't talked to Alex in 5 months" |
| Event-based | Context engine detected a relevant event | "Sarah just started a new job at Stripe" |
| Scheduled | User set a manual reminder | "Follow up with John after Q1" |

**Weekly digest:**
- Delivered every Monday morning (configurable)
- Contains 3-5 contacts, ranked by priority
- Each entry shows: name, reason for follow-up, last interaction date, suggested message
- Delivered via email and/or in-app notification

**User actions per suggestion:**
- **Edit & Send**, opens the message for editing, then sends via chosen channel
- **Schedule**, pick a date/time to send later
- **Snooze**, push this person back by 2 weeks / 1 month / 3 months
- **Dismiss**, skip this suggestion, no follow-up

---

### 4.8 AI Message Composer

**What it does:** Writes a draft follow-up message that sounds like the user, not like a bot.

**Inputs to the message generator:**

| Input | Purpose |
|-------|---------|
| Contact profile | Name, company, role |
| Last interaction summary | What you last talked about and when |
| Detected event (if any) | The reason for reaching out now |
| Conversation tone history | Formal vs. casual, based on past messages |
| User's writing style | Learned from sent messages over time |
| Preferred channel | Email vs. Twitter DM vs. Telegram |

**Example outputs:**

*Time-based, casual tone:*
> Hey Alex, it's been a minute. How's everything going with the new product? Would love to catch up sometime.

*Event-based, warm tone:*
> Saw your tweet about the seed round, congrats! That's a big milestone. How are things feeling now that it's closed?

*Re-engagement, professional tone:*
> Hi Sarah, hope you're doing well. I noticed you moved to Stripe. Congrats on the new role. Would be great to reconnect when you're settled in.

**What the composer does NOT do (MVP):**
- Send messages without user review
- Generate cold outreach to strangers
- Write multi-paragraph emails (keeps it short and natural)

---

### 4.9 Relationship Dashboard

**What it does:** The main screen. Shows the user what needs attention right now.

**Dashboard sections:**

**"Reach out this week"** (top, most prominent)
- 3-5 contact cards with follow-up reason and draft message
- One-click actions: send, edit, snooze, dismiss

**"Recent activity from your network"**
- Feed of detected events from contacts (job changes, tweets, milestones)
- Clickable to view full contact profile

**"Relationship health overview"**
- Simple breakdown: X active, Y warming, Z going cold
- Click any segment to see the contacts in that group

**"Recently contacted"**
- List of people you've interacted with in the last 7 days
- Confirms follow-throughs and keeps the loop closed

---

## 5. Data Model

### Core entities

```
Contact
├── id (uuid)
├── full_name
├── given_name
├── family_name
├── emails[] (array)
├── phones[] (array)
├── company
├── title
├── twitter_handle
├── telegram_username
├── tags[] (array)
├── notes (text)
├── relationship_score (int)
├── last_interaction_at (timestamp)
├── last_followup_at (timestamp)
├── priority_level (enum: high, medium, low)
├── source (enum: csv, google, manual, telegram, twitter)
├── created_at
└── updated_at

Interaction
├── id (uuid)
├── contact_id (fk)
├── platform (enum: email, telegram, twitter, manual)
├── direction (enum: inbound, outbound, mutual)
├── content_preview (text, truncated)
├── raw_reference_id (platform message ID)
├── occurred_at (timestamp)
└── created_at

DetectedEvent
├── id (uuid)
├── contact_id (fk)
├── event_type (enum: job_change, fundraising, product_launch,
│                     promotion, milestone, event_attendance)
├── confidence (float)
├── summary (text)
├── source_url (text)
├── detected_at (timestamp)
└── created_at

FollowUpSuggestion
├── id (uuid)
├── contact_id (fk)
├── trigger_type (enum: time_based, event_based, scheduled)
├── trigger_event_id (fk, nullable)
├── suggested_message (text)
├── suggested_channel (enum: email, telegram, twitter)
├── status (enum: pending, sent, snoozed, dismissed)
├── scheduled_for (timestamp, nullable)
├── created_at
└── updated_at

IdentityMatch
├── id (uuid)
├── contact_a_id (fk)
├── contact_b_id (fk)
├── match_score (float)
├── match_method (enum: deterministic, probabilistic, ai, user_confirmed)
├── status (enum: pending_review, merged, rejected)
├── created_at
└── resolved_at
```

---

## 6. Technical Architecture

```
┌─────────────────────────────────────────────┐
│                Data Sources                  │
│  Gmail API  ·  Telegram MTProto  ·  X API   │
│  CSV Upload · Google Contacts OAuth          │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│            Ingestion Layer                    │
│  Event listeners · Periodic sync jobs        │
│  (every 6-24h for Twitter, real-time for TG) │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│        Identity Resolution Engine            │
│  Deterministic → Probabilistic → AI → User   │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│        Unified Contact Graph (Postgres)      │
│  Contacts · Interactions · Events · Matches  │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│              AI Layer                         │
│  Context extraction · Event classification   │
│  Relationship scoring · Message generation   │
│  (LLM API + embeddings via vector DB)        │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────┐
│          Application Layer                    │
│  Web app (React/Next.js) · Email digests     │
│  Follow-up workflows · Notification system   │
└──────────────────────────────────────────────┘
```

**Stack:**

| Component | Technology |
|-----------|-----------|
| Backend | Python + FastAPI |
| Database | Postgres (relational), Vector DB for embeddings |
| Queue | Redis + Celery |
| AI | LLM API (Claude or GPT) for message gen and classification |
| Frontend | React or Next.js |
| Auth | OAuth 2.0 (Google, Twitter, Telegram) |
| Hosting | Cloud VPS or managed platform |

---

## 7. What's Explicitly Out of Scope for MVP

These are all valid features that belong in later versions, not v1.

| Feature | Why it's deferred |
|---------|-------------------|
| LinkedIn integration | API requires expensive partner approval |
| Fully autonomous messaging | Too risky for trust, users need to review first |
| Mobile app | Web-first, mobile later |
| Two-way Google Contacts sync | One-way import is simpler, avoids sync conflicts |
| Deep analytics and reporting | Nice to have, not core value |
| Team/shared CRM features | MVP is single-player |
| Cold outreach tools | Not the product's identity, risks "spam tool" perception |
| Calendar integration | Useful but adds scope without core value |

---

## 8. Build Roadmap

**Total estimated timeline:** 10-12 weeks for a solo developer or small team.

### Phase 1: Foundation (Weeks 1-4)

- User auth and onboarding
- CSV import and manual contact creation
- Google Contacts one-way sync
- Gmail API integration (thread sync, interaction tracking)
- Contact profile UI
- Interaction timeline
- Basic relationship scoring
- Postgres schema and API scaffolding

**Milestone:** User can import contacts, connect Gmail, and see a timeline of interactions.

### Phase 2: Intelligence (Weeks 5-8)

- Telegram integration (MTProto client)
- Identity resolution engine (Tier 1 deterministic + Tier 4 user confirmation)
- Context detection engine (Twitter activity polling + LLM classifier)
- AI message composer (draft generation)
- Follow-up suggestion engine (time-based + event-based triggers)
- Weekly digest (email delivery)

**Milestone:** User gets weekly follow-up suggestions with AI-drafted messages based on real context.

### Phase 3: Polish (Weeks 9-12)

- Twitter DM and mention sync
- Relationship dashboard UI
- Snooze, schedule, and dismiss flows
- Notification system
- Probabilistic identity matching (Tier 2)
- Edge case handling and error states
- Performance tuning for users with 500+ contacts

**Milestone:** Product is usable end-to-end. Ready for private beta.

---
