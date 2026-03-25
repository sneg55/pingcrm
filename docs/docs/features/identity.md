---
sidebar_position: 5
title: Identity Resolution
---

# Identity Resolution

The **Identity Resolution** page (`/identity`) detects and merges duplicate contacts that represent the same person across different platforms. PingCRM uses a multi-tier matching system to surface candidates, from deterministic exact matches to probabilistic scoring.

## Tier 1: Deterministic Matching

Tier 1 matches are high-confidence duplicates identified by exact data overlap. These are auto-merged without manual review.

Criteria:

- **Same email address** appears on two contact records.
- **Same phone number** appears on two contact records.
- **Email found in Twitter bio** links a Twitter-sourced contact to an email-sourced contact.

Because these signals are unique identifiers, false positives are extremely rare, and auto-merge is safe.

Deterministic matching also runs automatically after each platform sync (Gmail, Telegram, Twitter, LinkedIn). Contacts created during sync that share an email or phone number with an existing contact are merged immediately, preventing duplicate accumulation.

## Tier 2: Probabilistic Matching

When no exact identifier overlap exists, PingCRM computes a weighted similarity score across five signals:

| Signal | Weight |
|---|---|
| Email domain match | 40% |
| Name similarity | 20% |
| Company match | 20% |
| Username similarity | 10% |
| Mutual signals (shared groups, common connections) | 10% |

A combined score **above 85%** triggers an automatic merge. Scores below that threshold are surfaced for manual review.

### Colleague Guard

The colleague guard prevents false merges between coworkers. When two contacts share the same company but have clearly different names, the score is capped below the auto-merge threshold. This ensures that, for example, two employees at the same company with similar usernames are not incorrectly merged.

## Manual Review Queue

Candidates that score below the auto-merge threshold appear in the manual review queue. Each candidate pair is displayed as a **side-by-side comparison card** showing:

- Names, emails, and phone numbers from both records.
- Platform sources (Gmail, Telegram, Twitter, LinkedIn).
- Company and title information.
- Interaction history summaries.

For each pair, you can:

- **Merge** -- combines both records into a single contact, preserving all interactions and platform links.
- **Reject** -- dismisses the match so it will not be suggested again.

## On-Demand Scan

Click the **Scan** button on the Identity Resolution page to trigger a fresh duplicate detection pass across all contacts. This is useful after a large import or platform sync. The scan runs as a background task, and you will receive a notification when new matches are found.
