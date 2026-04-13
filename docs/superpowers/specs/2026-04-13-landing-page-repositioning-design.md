# Landing Page Repositioning: Self-Hosting as Primary CTA

## Problem

Visitors confuse the waitlist with product launch status. Three overlapping issues:

1. People think the waitlist is the only way to use PingCRM, missing that self-hosting is available now
2. The difference between self-hosted (available) and hosted (future) is unclear
3. "Waitlist" signals "not launched yet", undermining confidence that the product is ready

The current page has two competing CTAs in the hero ("Self-Host Now" + "Join Hosted Waitlist"), a nav link saying "Get Early Access", and a dedicated waitlist section at the bottom — all of which dilute the core message: PingCRM is available now.

## Target Audience

Both technical users (comfortable with Docker/servers) and semi-technical users (need guidance but can follow a setup guide). The page should serve both without requiring either to self-select.

## Changes

### 1. Hero Section

**Current:**
- Primary CTA: "Self-Host Now" (GitHub link)
- Secondary CTA: "Join Hosted Waitlist" (anchor to `#waitlist`)

**New:**
- Primary CTA: **"Self-Host Now"** (GitHub link) — unchanged
- Secondary CTA: **"Setup Guide"** (link to docs) — replaces waitlist CTA

Rationale: Two CTAs now serve two audiences (technical → GitHub, semi-technical → docs) instead of two products. No more competing signals.

### 2. Navigation Bar

**Current:**
- Right-side CTA: "Get Early Access" (anchor to `#waitlist`)

**New:**
- Right-side CTA: **"Get Started"** (link to docs or GitHub)

Rationale: "Get Early Access" implies the product isn't generally available. "Get Started" implies it is.

### 3. Open Source Section (mid-page)

**Current:**
- Heading, description, tech stack badges, "Star on GitHub" button

**New — additions only:**
- Add line beneath existing copy: **"Deploy in under 10 minutes with Docker Compose."**
- Optionally add **"Read the Docs"** as a secondary CTA alongside "Star on GitHub"

Rationale: Reassures semi-technical users that self-hosting isn't intimidating. Concrete time estimate ("10 minutes") is more persuasive than abstract "easy to deploy".

### 4. Waitlist Section → Removed

**Current:**
- Full dedicated `#waitlist` section with "HOSTED VERSION" label, heading, description, email form

**New:**
- Section deleted entirely
- Replaced by a **compact inline banner** positioned just above the footer
- Banner copy: "Prefer not to self-host? We're building a managed version." with inline email input and submit button
- Visually minimal — single row, muted styling, not a "section" with its own heading

### 5. Footer

**Current:**
- Logo, links (GitHub, Docs, Waitlist), credit

**New:**
- Add compact waitlist email capture as a footer column
- Label: "Hosted version coming soon" with inline email field
- Remove "Waitlist" from footer links (the form itself replaces it)

## What Stays the Same

- Hero headline and subheading copy
- "OPEN SOURCE - SELF-HOSTABLE" badge
- Features section (6-card grid)
- How It Works section (3 steps)
- Dashboard preview carousel
- Open Source section content (with minor addition)
- All visual design (colors, typography, animations)

## Technical Notes

- Waitlist form component (`waitlist-form.tsx`) can be reused — just rendered inline/compact instead of as a section
- Loops.so integration unchanged
- No new dependencies or API changes
- All changes are in the `landing/` directory
