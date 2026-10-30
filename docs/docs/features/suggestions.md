---
sidebar_position: 3
title: Follow-Up Suggestions
description: "PingCRM's follow-up suggestions use AI to recommend who to reach out to and why, so you maintain relationships before connections go cold."
---

# Follow-Up Suggestions

The `/suggestions` page lists AI-generated recommendations for who to contact and why. It is meant to catch relationships before they go cold.

![Suggestions inbox](/img/screenshots/suggestions/inbox.png)

## How Suggestions Are Generated

The follow-up engine runs daily at 08:00 UTC through Celery beat. The **Generate new suggestions** button on the page runs it on demand. Candidates come from two pools that share one budget.

By default the budget is **5 suggestions per run**: 3 slots for Pool A and 2 for Pool B. In Settings, under **Follow-up Rules**, you can raise **Max suggestions per batch** to anywhere from 5 to 20 (the setting defaults to 10 once saved). The budget then splits roughly 60% to Pool A and 40% to Pool B. When one pool has fewer candidates than slots, the other pool uses the spare slots.

### Pool A: Active Relationships (3 slots by default)

Pool A has four independent triggers, and a contact needs to match only one:

| Trigger | Condition | Example |
|---|---|---|
| **Time-based** | No interaction within the contact's priority interval (high 30d / medium 60d / low 180d), relationship score below 4, and at least 1 past interaction (3 for low priority) | "Haven't talked to Alex in 3 months" |
| **Event-based** | A detected event in the last 7 days with confidence above 70%, and the last interaction at least 14 days ago | Bio change, tweet about fundraising |
| **Scheduled** | The last follow-up is older than the priority interval | Medium priority set to 60 days, last follow-up was 65 days ago |
| **Birthday** | Birthday today or within the next 3 days | Priority 1500, ignores the interaction requirement |

Pool A only includes contacts whose last interaction falls within the dormancy threshold (365 days by default). Contacts with a relationship score of 0 and no interaction in over a year are dropped from the time-based and scheduled triggers. The priority intervals can be changed per priority level in Settings (defaults: high 30d, medium 60d, low 180d).

### Pool B: Dormant Revival (2 slots by default)

Pool B surfaces contacts you lost touch with but once engaged with. It has three sub-triggers, and every contact needs a relationship score above 0:

| Trigger | Condition |
|---|---|
| **B1: Deep dormant** | No interaction for 365 days to 5 years, and either 5+ past interactions or a score of 5 or more |
| **B2: Mid dormant** | No interaction for 365 days to 3 years, and 2+ past interactions |
| **B3: Event revival** | Dormant past the threshold (365 days by default), with a detected event in the last 14 days (job change, for example) and some history (2+ interactions, a score of 3 or more, or a 30-day span between first and last interaction) |

Under **Follow-up Rules** you can turn off dormant revival entirely and change the dormancy threshold (30 to 3650 days).

### Cooldowns and Guards

These guards apply to every trigger, event-based included. The birthday trigger is exempt from the interaction cooldown:

| Guard | Rule |
|---|---|
| **Interaction cooldown** | Skip if the last interaction was within **14 days** |
| **Follow-up cooldown** | Skip if the last follow-up was within **14 days** |
| **Already queued** | Skip if a pending or snoozed suggestion already exists |
| **Dismissed by you** | Skip for 30 days after you dismissed a suggestion for the contact. Dismissals made by the system do not count. |
| **Archived** | Skip archived contacts |
| **2nd-tier** | Skip contacts tagged "2nd tier" |
| **No channel** | Skip contacts with no email, Telegram, Twitter, or LinkedIn |
| **Ghosting (3+)** | Skip if the last 3 interactions are all outbound with no reply and the most recent was within 30 days |
| **Ghosting (2)** | Halve the priority if the last 2 interactions are outbound and the most recent was within 30 days |
| **Unread outbound** | Skip if the last outbound Telegram message has not been read |
| **Read no reply** | Add 100 to the priority if the last outbound Telegram message was read but got no reply |

### Priority Scoring

Within each pool, candidates are ranked by priority score.

Pool A:

- Contacts with 10+ interactions get a base of 1000 when the last interaction was more than 90 days ago, or 500 when it was 14 to 90 days ago. Every contact adds its interaction count.
- Event-based triggers add 200.
- Birthdays are fixed at 1500.

Pool B:

- Interactions of 8+ or a score of 5+ give a base of 1000. Interactions of 4+ or a score of 3+ give 500.
- The interaction count is added, along with 150 when the history spans at least 180 days and 300 for event revival.

### Relationship Score

The relationship score (0 to 10) adds up points from several dimensions, plus a tenure bonus, and is capped at 10. A Celery beat task recalculates it daily at 02:00 UTC:

| Dimension | Points | What it measures |
|---|---|---|
| Reciprocity | 0-4 | Balance of inbound and outbound, as the min/max ratio over the last year |
| Recency | 0-3 | Last inbound message: 3 within 7 days, 2 within 30, 1 within 90. Halved (rounded) when there is no inbound message at all. |
| Frequency | 0-2 | Weighted interaction counts across time windows: 1 at a weight of 3, 2 at a weight of 8 |
| Breadth | 0-1 | 1 point for interactions on 2 or more platforms |
| Tenure | 0-2 | 1 point for 20+ interactions over at least a year, 2 points for 50+ interactions over at least 2 years |

**Extended decay:** interactions from 1 to 2 years ago still count at 0.05x weight, and those from 2 to 5 years ago at 0.02x. Long-term contacts therefore do not drop to zero.

### Event Classification

Bio changes found by the daily Twitter profile poll create `DetectedEvent` records. When composing suggestions, the engine also fetches recent tweets on demand through [Bird CLI](./twitter.md#bird-cli-steipetebird), caches them in Redis for 12 hours, and classifies them with Claude into categories such as job changes, fundraising, and product launches.

The daily cron does not fetch or classify tweets. That happens only for contacts that need a suggestion.

## AI Message Composer

Each suggestion includes a message drafted by Claude. The draft draws on:

- The contact's profile, company, and bio.
- The last 5 interactions, to match tone (formal or casual).
- Any detected events, such as a job change or fundraising.
- Recent Twitter activity (bio and last 5 tweets), fetched on demand for every trigger type and cached for 12 hours.
- The contact's preferred channel, based on the platform of the most recent interaction.

When the last conversation is 90+ days old and a tweet from the last 30 days exists, the prompt tells the model to anchor the message on the fresh tweet and not reopen the stale thread.

![Expanded suggestion card with AI-drafted message](/img/screenshots/suggestions/card-expanded.png)

## Contact Avatars

When a contact has an avatar (from Google Contacts, Telegram, Twitter, or LinkedIn), it appears next to the suggestion.

## Actions

For each suggestion you can:

- **Edit and send** the AI-drafted message. Telegram messages are sent from PingCRM and can be scheduled. For email and Twitter, the message is copied to the clipboard, and the Twitter profile opens in a new tab. Marking a suggestion sent records a follow-up on the contact.
- **Regenerate** the draft, optionally for a different channel.
- **Snooze** the suggestion for 2 weeks, 1 month, or 3 months.

  ![Snooze duration menu](/img/screenshots/suggestions/snooze-menu.png)

  An hourly Celery beat task reactivates snoozed suggestions when the snooze ends.
- **Dismiss** the suggestion. The engine will not suggest that contact again for 30 days.

Opening the page also dismisses any pending suggestion for a contact who has interacted with you since the suggestion was created.
