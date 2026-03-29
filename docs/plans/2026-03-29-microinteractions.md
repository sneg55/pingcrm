# Microinteractions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add polished microinteractions (entrance animations, card hovers, button feedback, menu animations, number counters, shimmer loading, success feedback, scroll reveals) across all PingCRM pages using pure CSS + one React component.

**Architecture:** All animations defined as CSS utility classes in `globals.css`. Applied via `className` strings on existing components. One new `<AnimatedNumber>` component for counter animations. Landing page gets Intersection Observer scroll reveals. No new dependencies.

**Tech Stack:** CSS keyframes, Tailwind utilities, React (one component), Intersection Observer API

**Spec:** `docs/specs/2026-03-29-microinteractions-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `frontend/src/app/globals.css` | All new keyframes + utility classes + accessibility |
| Create | `frontend/src/components/animated-number.tsx` | Counter animation component |
| Modify | `frontend/src/app/dashboard/page.tsx` | Stagger entrances + AnimatedNumber on stats |
| Modify | `frontend/src/app/contacts/page.tsx` | Stagger + card-hover on rows |
| Modify | `frontend/src/app/suggestions/page.tsx` | Stagger + card-hover on cards |
| Modify | `frontend/src/app/settings/page.tsx` | Stagger on platform cards |
| Modify | `frontend/src/app/contacts/[id]/page.tsx` | Stagger on sidebar sections |
| Modify | `frontend/src/app/contacts/[id]/_components/message-composer-card.tsx` | Flash success on send |
| Modify | `frontend/src/app/contacts/[id]/_components/header-card.tsx` | btn-press on action buttons |
| Modify | `frontend/src/components/nav.tsx` | menu-enter on dropdowns |
| Modify | `frontend/src/app/identity/page.tsx` | card-hover + stagger on match cards |
| Modify | `frontend/src/app/organizations/page.tsx` | card-hover + stagger on org grid |
| Modify | `landing/app/globals.css` | scroll-reveal classes |
| Modify | `landing/app/page.tsx` | Intersection Observer + scroll-reveal classes |

---

## Task 1: CSS Foundation — all keyframes + utility classes

**Files:**
- Modify: `frontend/src/app/globals.css`

- [ ] **Step 1: Add new keyframes and utility classes to globals.css**

Append after the existing `.font-mono-data` block at the end of the file:

```css
/* ── Microinteractions ── */

/* Staggered entrance animation */
.animate-in {
  animation: fade-in-up 0.4s ease-out both;
  opacity: 0;
}
.stagger-1 { animation-delay: 50ms; }
.stagger-2 { animation-delay: 100ms; }
.stagger-3 { animation-delay: 150ms; }
.stagger-4 { animation-delay: 200ms; }
.stagger-5 { animation-delay: 250ms; }
.stagger-6 { animation-delay: 300ms; }
.stagger-7 { animation-delay: 350ms; }
.stagger-8 { animation-delay: 400ms; }

/* Menu/dropdown entrance */
@keyframes menu-in {
  from { opacity: 0; transform: scale(0.95) translateY(-4px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}
.menu-enter {
  animation: menu-in 150ms ease-out;
  transform-origin: top right;
}

/* Success pulse ring (send/save buttons) */
@keyframes success-pulse {
  0% { box-shadow: 0 0 0 0 rgba(20,184,166,0.4); }
  100% { box-shadow: 0 0 0 12px transparent; }
}
.btn-success-pulse {
  animation: success-pulse 0.6s ease-out;
}

/* Success flash border (cards) */
@keyframes flash-success {
  0% { box-shadow: 0 0 0 2px rgba(20,184,166,0.5); }
  100% { box-shadow: 0 0 0 0 transparent; }
}
.flash-success {
  animation: flash-success 1s ease-out;
}

/* Toast slide in from right */
@keyframes slide-in-right {
  from { transform: translateX(100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}
.toast-enter {
  animation: slide-in-right 300ms ease-out;
}

/* Shimmer loading (replaces animate-pulse) */
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.shimmer {
  background: linear-gradient(
    90deg,
    transparent 25%,
    rgba(255,255,255,0.05) 50%,
    transparent 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s linear infinite;
}

/* Accessibility: respect reduced motion preference */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/globals.css
git commit -m "feat: add microinteraction CSS foundation (keyframes + utility classes)"
```

---

## Task 2: AnimatedNumber component

**Files:**
- Create: `frontend/src/components/animated-number.tsx`

- [ ] **Step 1: Create the component**

```tsx
"use client";

import { useEffect, useRef, useState } from "react";

interface AnimatedNumberProps {
  value: number;
  duration?: number;
  className?: string;
}

export function AnimatedNumber({ value, duration = 600, className }: AnimatedNumberProps) {
  const [display, setDisplay] = useState(0);
  const prevValue = useRef(0);

  useEffect(() => {
    const start = prevValue.current;
    const end = value;
    if (start === end) return;

    const startTime = performance.now();

    function tick(now: number) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = Math.round(start + (end - start) * eased);
      setDisplay(current);

      if (progress < 1) {
        requestAnimationFrame(tick);
      } else {
        prevValue.current = end;
      }
    }

    requestAnimationFrame(tick);
  }, [value, duration]);

  return <span className={className}>{display.toLocaleString()}</span>;
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/animated-number.tsx
git commit -m "feat: add AnimatedNumber counter component"
```

---

## Task 3: Dashboard — stagger entrances + animated counters

**Files:**
- Modify: `frontend/src/app/dashboard/page.tsx`

- [ ] **Step 1: Apply animations to dashboard**

Read the dashboard page, then make these changes:

1. Import `AnimatedNumber`:
```tsx
import { AnimatedNumber } from "@/components/animated-number";
```

2. Wrap the stat cards grid in `<div className="animate-in stagger-1">`:
```tsx
{!isEmpty && (
  <div className="animate-in stagger-1 grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
```

3. Replace raw stat numbers with `<AnimatedNumber>` in each StatCard. Find where `stats.total`, `stats.active`, `stats.interactionsThisWeek` are rendered and wrap them:
```tsx
<AnimatedNumber value={stats.total} className="..." />
```
(Keep existing className for the number display)

4. Wrap the two-column layout sections:
```tsx
{/* Pending Follow-ups */}
<div className="animate-in stagger-2">
  ...
</div>

{/* Recent Activity */}
<div className="animate-in stagger-3">
  ...
</div>

{/* Needs Attention */}
<div className="animate-in stagger-2">
  ...
</div>
```

5. Add `card-hover` to overdue contact rows and activity items.

- [ ] **Step 2: Verify build + visual check**

Run: `cd frontend && npm run build`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/dashboard/page.tsx
git commit -m "feat: add entrance animations + animated counters to dashboard"
```

---

## Task 4: Contacts list — stagger + card hover

**Files:**
- Modify: `frontend/src/app/contacts/page.tsx` (or the contacts list component if decomposed)

- [ ] **Step 1: Apply animations**

1. Wrap the toolbar/filter section in `<div className="animate-in stagger-1">`
2. Wrap the contacts table/list in `<div className="animate-in stagger-2">`
3. Add `card-hover` class to each contact row's outer container

- [ ] **Step 2: Commit**

```bash
git commit -m "feat: add entrance animations + card hover to contacts list"
```

---

## Task 5: Suggestions, Identity, Organizations pages

**Files:**
- Modify: `frontend/src/app/suggestions/page.tsx`
- Modify: `frontend/src/app/identity/page.tsx`
- Modify: `frontend/src/app/organizations/page.tsx`

- [ ] **Step 1: Suggestions page**

1. Wrap the header area in `animate-in stagger-1`
2. Wrap the suggestion cards container in `animate-in stagger-2`
3. Add `card-hover` to each suggestion card

- [ ] **Step 2: Identity page**

1. Wrap the scan button area in `animate-in stagger-1`
2. Wrap the match cards container in `animate-in stagger-2`
3. Add `card-hover` to each identity match pair card

- [ ] **Step 3: Organizations page**

1. Wrap the header in `animate-in stagger-1`
2. Wrap the org grid in `animate-in stagger-2`
3. Add `card-hover` to each org card

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: add entrance animations + card hover to suggestions, identity, orgs pages"
```

---

## Task 6: Contact detail + Settings — stagger + button press

**Files:**
- Modify: `frontend/src/app/contacts/[id]/page.tsx`
- Modify: `frontend/src/app/contacts/[id]/_components/header-card.tsx`
- Modify: `frontend/src/app/settings/page.tsx`

- [ ] **Step 1: Contact detail page**

1. Wrap the header card in `animate-in stagger-1`
2. Wrap the main column (composer + timeline) in `animate-in stagger-2`
3. Wrap the sidebar in `animate-in stagger-3`

- [ ] **Step 2: Header card buttons**

Add `btn-press` class to all action buttons in header-card.tsx (priority buttons, archive, kebab trigger).

- [ ] **Step 3: Settings page**

Wrap each platform card section in `animate-in stagger-N` (incrementing N per card).

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: add entrance animations to contact detail + settings pages"
```

---

## Task 7: Dropdown/menu animations

**Files:**
- Modify: `frontend/src/components/nav.tsx`
- Modify: `frontend/src/app/contacts/[id]/_components/header-card.tsx`
- Modify: `frontend/src/app/contacts/[id]/_components/message-composer-card.tsx`

- [ ] **Step 1: Nav user dropdown**

Find the dropdown menu div that renders when user menu is open. Add `menu-enter` class to the dropdown container.

- [ ] **Step 2: Contact detail kebab menu**

In header-card.tsx, find the kebab dropdown div (the one rendered when `menuOpen` is true). Add `menu-enter` class.

- [ ] **Step 3: Snooze dropdown**

In message-composer-card.tsx, find the snooze options dropdown. Add `menu-enter` class.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: add menu entrance animations to dropdowns"
```

---

## Task 8: Shimmer loading states

**Files:**
- Modify: `frontend/src/app/dashboard/page.tsx`
- Modify: `frontend/src/app/contacts/[id]/page.tsx`

- [ ] **Step 1: Replace animate-pulse with shimmer**

Search for `animate-pulse` in the dashboard and contact detail loading skeletons. For each skeleton placeholder div, add the `shimmer` class alongside the existing background color:

```tsx
// Before:
<div className="h-6 w-48 bg-stone-200 dark:bg-stone-800 rounded animate-pulse" />

// After:
<div className="h-6 w-48 bg-stone-200 dark:bg-stone-800 rounded shimmer" />
```

Do this for all skeleton elements in:
- Dashboard stat card skeletons
- Dashboard suggestion/activity skeletons
- Contact detail header skeleton
- Contact detail sidebar skeleton

- [ ] **Step 2: Commit**

```bash
git commit -m "feat: replace animate-pulse with shimmer gradient on loading skeletons"
```

---

## Task 9: Success feedback — flash + composer

**Files:**
- Modify: `frontend/src/app/contacts/[id]/_components/message-composer-card.tsx`

- [ ] **Step 1: Add flash-success on message send**

In message-composer-card.tsx, after a successful send (in the `handleSend` success path), add the `flash-success` class to the card wrapper temporarily:

```tsx
// In the handleSend success path, after setSent():
const cardEl = document.querySelector('[data-composer-card]');
if (cardEl) {
  cardEl.classList.add('flash-success');
  setTimeout(() => cardEl.classList.remove('flash-success'), 1000);
}
```

Add `data-composer-card` attribute to the card's outer div.

Alternatively, use a state variable:
```tsx
const [flashSuccess, setFlashSuccess] = useState(false);

// In handleSend success:
setFlashSuccess(true);
setTimeout(() => setFlashSuccess(false), 1000);

// On the card div:
className={cn("...", flashSuccess && "flash-success")}
```

- [ ] **Step 2: Commit**

```bash
git commit -m "feat: add success flash animation on message send"
```

---

## Task 10: Landing page — scroll reveal

**Files:**
- Modify: `landing/app/globals.css`
- Modify: `landing/app/page.tsx`

- [ ] **Step 1: Add scroll-reveal CSS to landing globals**

Append to `landing/app/globals.css`:

```css
/* Scroll-triggered reveal */
.scroll-reveal {
  opacity: 0;
  transform: translateY(24px);
  transition: opacity 0.6s ease-out, transform 0.6s ease-out;
}
.scroll-reveal.visible {
  opacity: 1;
  transform: translateY(0);
}
```

- [ ] **Step 2: Add Intersection Observer to landing page**

In `landing/app/page.tsx`, add a `useEffect` that sets up the observer:

```tsx
useEffect(() => {
  const els = document.querySelectorAll('.scroll-reveal');
  if (!els.length) return;
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.1 }
  );
  els.forEach((el) => observer.observe(el));
  return () => observer.disconnect();
}, []);
```

- [ ] **Step 3: Apply scroll-reveal to sections**

Add `scroll-reveal` class to:
- Feature cards grid container
- Any testimonial/social proof sections
- Pricing section (if exists)
- Bottom CTA section

Keep the hero section as-is (it uses existing fade-up-on-load).

- [ ] **Step 4: Verify build**

Run: `cd landing && npm run build`

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add scroll-triggered reveal animations to landing page"
```

---

## Task 11: Final build verification

- [ ] **Step 1: Build frontend**

```bash
cd frontend && npm run build
```

- [ ] **Step 2: Build landing**

```bash
cd landing && npm run build
```

- [ ] **Step 3: Run frontend tests**

```bash
cd frontend && npx vitest run
```

- [ ] **Step 4: Visual spot-check**

Open the app locally and verify:
- Dashboard cards cascade in on load
- Stat numbers count up
- Contact rows lift on hover
- Kebab menu animates open
- Loading skeletons shimmer
- Landing page sections reveal on scroll
