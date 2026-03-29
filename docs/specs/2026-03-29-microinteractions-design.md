# Microinteractions Design

**Date:** 2026-03-29
**Status:** Approved

## Problem

PingCRM's UI feels static — interactions happen instantly with minimal visual feedback. The landing page has staggered fade-ups but the app itself relies on basic Tailwind color transitions only.

## Solution

Add polished microinteractions across all pages using pure CSS + one small React component. No new dependencies. "Polished & Energetic" personality — smooth 200-400ms ease-out animations, card lifts, staggered entrances, number counters, shimmer loading.

## Approach

CSS-only. All animations defined as utility classes in `globals.css`. Applied via className strings — no animation library, no spring physics, no page route transitions.

## 1. Page Entrance Animations

Staggered fade-up when navigating to any page. Cards and sections cascade in with 50ms delays.

```css
.animate-in {
  animation: fadeInUp 0.4s ease-out both;
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
```

**Applied to:** Dashboard stat cards, suggestion list, activity feed, contacts table header + rows, settings platform cards, identity match cards, org grid, contact detail sidebar sections.

**Pattern:** Wrap each section in `<div className="animate-in stagger-N">` where N increments per section on the page.

## 2. Card Hover Effects

Interactive list items lift 1px with deepening shadow on hover.

```css
.card-hover {
  transition: transform 200ms ease-out, box-shadow 200ms ease-out;
}
.card-hover:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}
/* Dark mode */
.dark .card-hover:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}
```

**Applied to:** Contact rows, suggestion cards, notification items, org cards, activity items, identity match pair cards, dashboard overdue rows.

## 3. Button Press Feedback

All clickable buttons get tactile scale-down on press. Send/submit buttons get a success pulse ring.

```css
.btn-press:active {
  transform: scale(0.97);
  transition: transform 100ms ease-out;
}

@keyframes successPulse {
  0% { box-shadow: 0 0 0 0 rgba(20,184,166,0.4); }
  100% { box-shadow: 0 0 0 12px transparent; }
}
.btn-success-pulse {
  animation: successPulse 0.6s ease-out;
}
```

**Applied to:** All buttons site-wide via `btn-press`. Success pulse on: Send message, Generate suggestions, Sync now, Save settings.

## 4. Dropdown/Menu Animations

Menus scale from origin point with fade, instead of appearing instantly.

```css
@keyframes menuIn {
  from { opacity: 0; transform: scale(0.95) translateY(-4px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}
.menu-enter {
  animation: menuIn 150ms ease-out;
  transform-origin: top right;
}
```

**Applied to:** Kebab menus (contact detail, settings cards), snooze picker, tag autocomplete dropdown, nav user dropdown, filter dropdowns on contacts page.

## 5. Animated Number Counters

Dashboard stat cards count up from 0 to their value over 600ms on page load.

**Component:** `frontend/src/components/animated-number.tsx` (~25 lines)

```typescript
// Uses requestAnimationFrame to animate from 0 to target
// Easing: ease-out cubic
// Duration: 600ms
// Formats with toLocaleString() for commas
```

**Applied to:** Dashboard stat cards (Total contacts, Active relationships, Interactions this week). Notification unread badge count.

## 6. Shimmer Loading States

Replace `animate-pulse` gray boxes with a shimmer gradient sweep.

```css
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.shimmer {
  background: linear-gradient(
    90deg,
    rgba(255,255,255,0) 25%,
    rgba(255,255,255,0.05) 50%,
    rgba(255,255,255,0) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s linear infinite;
}
```

**Applied to:** All skeleton loading states — dashboard cards, contact list rows, contact detail page, settings cards, suggestions list.

## 7. Success/Action Feedback

Brief visual feedback when actions complete.

```css
@keyframes flashSuccess {
  0% { box-shadow: 0 0 0 2px rgba(20,184,166,0.5); }
  100% { box-shadow: 0 0 0 0 transparent; }
}
.flash-success {
  animation: flashSuccess 1s ease-out;
}

@keyframes slideInRight {
  from { transform: translateX(100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}
.toast-enter {
  animation: slideInRight 300ms ease-out;
}
```

**Flash applied to:** Message composer card after send, contact detail card after save, settings card after sync complete.

**Toast:** Sync complete notifications, error messages. Slide in from right, auto-dismiss after 4s.

## 8. Landing Page Polish

Scroll-triggered reveal for sections below the fold using Intersection Observer.

```css
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

**Intersection Observer:** ~15 lines of vanilla JS in a `<script>` tag or a small `useScrollReveal` hook. Triggers `.visible` when element enters viewport with 10% threshold.

**Applied to:** Feature cards grid, testimonials, pricing section, bottom CTA. Hero section keeps existing fade-up-on-load.

**CTA button shimmer:** Gradient sweep on hover (already exists in landing CSS, extend to more buttons).

## Files Changed

| File | Changes |
|------|---------|
| `frontend/src/app/globals.css` | New keyframes: menuIn, successPulse, flashSuccess, slideInRight, shimmer. New classes: animate-in, stagger-1..8, card-hover (extend), btn-press (extend), menu-enter, shimmer, flash-success, toast-enter |
| `frontend/src/components/animated-number.tsx` | New component: counter animation (~25 lines) |
| `frontend/src/app/dashboard/page.tsx` | animate-in stagger on sections, AnimatedNumber on stat cards |
| `frontend/src/app/contacts/page.tsx` | animate-in on table, card-hover on rows |
| `frontend/src/app/suggestions/page.tsx` | animate-in + card-hover on suggestion cards |
| `frontend/src/app/settings/page.tsx` | animate-in on platform cards |
| `frontend/src/app/contacts/[id]/page.tsx` | animate-in on sidebar sections |
| `frontend/src/app/contacts/[id]/_components/header-card.tsx` | btn-press on buttons |
| `frontend/src/app/contacts/[id]/_components/message-composer-card.tsx` | flash-success on send |
| `frontend/src/components/nav.tsx` | menu-enter on user dropdown |
| `frontend/src/app/identity/page.tsx` | card-hover + animate-in on match cards |
| `frontend/src/app/organizations/page.tsx` | card-hover + animate-in on org cards |
| Various dropdown/menu components | menu-enter class |
| `landing/app/page.tsx` | Intersection observer for scroll-reveal |
| `landing/app/globals.css` | scroll-reveal + visible classes |

## Accessibility

All animations respect `prefers-reduced-motion`:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

Added once in `globals.css`. Disables all animations for users who have reduced motion enabled in their OS settings.

## What's NOT Included

- No framer-motion or animation libraries
- No Next.js page route transitions (not supported CSS-only)
- No confetti or particle effects
- No spring physics
- No layout animations (elements repositioning)
- No sound effects

## Testing

- Visual verification only — no automated tests for animations
- Verify `prefers-reduced-motion` media query disables animations for accessibility
- Check animations don't cause layout shifts (CLS)
