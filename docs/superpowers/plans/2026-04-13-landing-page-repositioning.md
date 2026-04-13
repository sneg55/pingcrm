# Landing Page Repositioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reposition the landing page to make self-hosting the primary action, demoting the hosted waitlist to a minimal footer presence.

**Architecture:** All changes are in `landing/app/`. The WaitlistForm component gets a `compact` prop for inline rendering. The dedicated waitlist section is removed and replaced by a compact banner above the footer. Nav and hero CTAs are reworded to drive self-hosting.

**Tech Stack:** Next.js, React, TypeScript, Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-04-13-landing-page-repositioning-design.md`

---

### Task 1: Add compact variant to WaitlistForm

**Files:**
- Modify: `landing/app/waitlist-form.tsx`

- [ ] **Step 1: Add `compact` prop and update component signature**

In `landing/app/waitlist-form.tsx`, change the component signature and adjust the success and form rendering for compact mode:

```tsx
export default function WaitlistForm({ compact = false }: { compact?: boolean }) {
```

- [ ] **Step 2: Update success state for compact mode**

Replace the current success return block (lines 46-58) with:

```tsx
  if (status === "success") {
    return (
      <div className={`flex items-center gap-2 ${compact ? "px-3 py-2" : "px-6 py-4"} rounded-lg border`}
        style={{ borderColor: "var(--accent-dim)", background: "var(--accent-glow)" }}>
        <svg width={compact ? 14 : 20} height={compact ? 14 : 20} viewBox="0 0 20 20" fill="none" className="shrink-0">
          <path d="M7 10l2 2 4-4" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="10" cy="10" r="8" stroke="var(--accent)" strokeWidth="1.5" />
        </svg>
        <span style={{ color: "var(--accent)", fontFamily: "'Space Mono', monospace", fontSize: compact ? "12px" : "14px" }}>
          {message}
        </span>
      </div>
    );
  }
```

- [ ] **Step 3: Update form rendering for compact mode**

Replace the form return (lines 60-109) with:

```tsx
  return (
    <form onSubmit={handleSubmit} className={`flex ${compact ? "flex-row gap-2" : "flex-col sm:flex-row gap-3"} w-full ${compact ? "max-w-md" : "max-w-lg"}`}>
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@company.com"
        required
        className={`flex-1 ${compact ? "px-3 py-1.5" : "px-4 py-3"} rounded-lg text-sm`}
        style={{
          fontFamily: "'Space Mono', monospace",
          background: "var(--bg-surface)",
          border: "1px solid var(--border)",
          color: "var(--text)",
          fontSize: compact ? "12px" : "14px",
        }}
      />
      <button
        type="submit"
        disabled={status === "loading"}
        className={`${compact ? "px-4 py-1.5" : "px-6 py-3"} rounded-lg text-sm font-bold tracking-wide whitespace-nowrap transition-all duration-200 cursor-pointer`}
        style={{
          fontFamily: "'Space Mono', monospace",
          background: status === "loading"
            ? "var(--border)"
            : "linear-gradient(135deg, var(--accent-dim), var(--accent))",
          color: "var(--bg)",
          fontSize: compact ? "12px" : "14px",
          border: "none",
        }}
        onMouseEnter={(e) => {
          if (status !== "loading") {
            e.currentTarget.style.boxShadow = "0 0 24px var(--accent-glow-strong), 0 4px 16px var(--accent-glow)";
            e.currentTarget.style.transform = "translateY(-1px)";
          }
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.boxShadow = "none";
          e.currentTarget.style.transform = "translateY(0)";
        }}
      >
        {status === "loading" ? "Joining..." : "Join Waitlist"}
      </button>
      {status === "error" && (
        <p className="text-sm mt-1" style={{ color: "#ef4444", fontFamily: "'Space Mono', monospace", fontSize: "12px" }}>
          {message}
        </p>
      )}
    </form>
  );
```

- [ ] **Step 4: Verify the page still renders**

Run: `cd /Users/sneg55-pro13/Documents/github/pingcrm/landing && npm run build 2>&1 | tail -20`
Expected: Build succeeds with no errors.

- [ ] **Step 5: Commit**

```bash
git add landing/app/waitlist-form.tsx
git commit -m "feat(landing): add compact variant to WaitlistForm"
```

---

### Task 2: Update hero CTAs

**Files:**
- Modify: `landing/app/page.tsx` (lines 208-237)

- [ ] **Step 1: Replace "Join Hosted Waitlist" button with "Setup Guide"**

In `landing/app/page.tsx`, find and replace the hero CTA block (lines 224-236):

```tsx
            <a
              href="#waitlist"
              className="flex items-center gap-2 px-6 py-3 rounded-lg text-sm tracking-wide transition-all duration-200 hover:border-[var(--border-bright)] hover:-translate-y-0.5"
              style={{
                fontFamily: "'Space Mono', monospace",
                border: "1px solid var(--border-bright)",
                background: "var(--bg-elevated)",
                color: "var(--text)",
                fontSize: "14px",
              }}
            >
              Join Hosted Waitlist
            </a>
```

Replace with:

```tsx
            <a
              href="https://docs.pingcrm.xyz/"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-6 py-3 rounded-lg text-sm tracking-wide transition-all duration-200 hover:border-[var(--border-bright)] hover:-translate-y-0.5"
              style={{
                fontFamily: "'Space Mono', monospace",
                border: "1px solid var(--border-bright)",
                background: "var(--bg-elevated)",
                color: "var(--text)",
                fontSize: "14px",
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z" />
                <path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z" />
              </svg>
              Setup Guide
            </a>
```

- [ ] **Step 2: Commit**

```bash
git add landing/app/page.tsx
git commit -m "feat(landing): replace waitlist CTA with Setup Guide in hero"
```

---

### Task 3: Update nav CTA

**Files:**
- Modify: `landing/app/nav.tsx` (lines 68-79)

- [ ] **Step 1: Replace "Get Early Access" with "Get Started"**

In `landing/app/nav.tsx`, find and replace the nav CTA (lines 68-79):

```tsx
          <a
            href="#waitlist"
            className="px-4 py-1.5 rounded text-sm transition-all duration-200 hover:shadow-[0_0_16px_var(--accent-glow)]"
            style={{
              fontFamily: "'Space Mono', monospace",
              fontSize: "13px",
              border: "1px solid var(--accent-dim)",
              color: "var(--accent)",
            }}
          >
            Get Early Access
          </a>
```

Replace with:

```tsx
          <a
            href="https://docs.pingcrm.xyz/"
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-1.5 rounded text-sm transition-all duration-200 hover:shadow-[0_0_16px_var(--accent-glow)]"
            style={{
              fontFamily: "'Space Mono', monospace",
              fontSize: "13px",
              border: "1px solid var(--accent-dim)",
              color: "var(--accent)",
            }}
          >
            Get Started
          </a>
```

- [ ] **Step 2: Commit**

```bash
git add landing/app/nav.tsx
git commit -m "feat(landing): replace Get Early Access with Get Started in nav"
```

---

### Task 4: Add deploy time estimate and docs CTA to Open Source section

**Files:**
- Modify: `landing/app/page.tsx` (lines 349-402)

- [ ] **Step 1: Add deploy time estimate after the description paragraph**

In `landing/app/page.tsx`, find the paragraph ending with "No vendor lock-in, no data harvesting." (line 365) and add a new line after the closing `</p>` tag (after line 365):

```tsx
          <p className="text-sm mb-8" style={{ color: "var(--accent)", fontFamily: "'Space Mono', monospace" }}>
            Deploy in under 10 minutes with Docker Compose.
          </p>
```

Also change the preceding paragraph's `mb-8` to `mb-3` so the spacing flows correctly. The paragraph on line 363 becomes:

```tsx
          <p className="text-lg leading-relaxed mb-3 max-w-xl mx-auto" style={{ color: "var(--text-muted)" }}>
```

- [ ] **Step 2: Add "Read the Docs" as secondary CTA next to "Star on GitHub"**

Find the "Star on GitHub" link (lines 385-400). Wrap it and a new link in a flex container. Replace the single `<a>` with:

```tsx
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2.5 px-6 py-3 rounded-lg text-sm font-bold tracking-wide transition-all duration-200 hover:border-[var(--text-muted)] hover:-translate-y-0.5"
              style={{
                fontFamily: "'Space Mono', monospace",
                border: "1px solid var(--border-bright)",
                background: "var(--bg-elevated)",
                color: "var(--text)",
                fontSize: "14px",
              }}
            >
              <GitHubIcon size={18} />
              Star on GitHub
            </a>
            <a
              href="https://docs.pingcrm.xyz/"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2.5 px-6 py-3 rounded-lg text-sm tracking-wide transition-all duration-200 hover:border-[var(--text-muted)] hover:-translate-y-0.5"
              style={{
                fontFamily: "'Space Mono', monospace",
                border: "1px solid var(--border)",
                color: "var(--text-muted)",
                fontSize: "14px",
              }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z" />
                <path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z" />
              </svg>
              Read the Docs
            </a>
          </div>
```

- [ ] **Step 3: Commit**

```bash
git add landing/app/page.tsx
git commit -m "feat(landing): add deploy time estimate and docs CTA to open source section"
```

---

### Task 5: Remove waitlist section, add compact banner, update footer

**Files:**
- Modify: `landing/app/page.tsx` (waitlist section)
- Modify: `landing/app/nav.tsx` (footer)

- [ ] **Step 1: Remove the entire waitlist section from page.tsx**

In `landing/app/page.tsx`, delete the waitlist section (everything from `{/* ──── Waitlist ──── */}` through the closing `</section>` — lines 406-431).

Also remove the `WaitlistForm` import on line 1 since the page no longer uses it directly.

- [ ] **Step 2: Add compact waitlist banner above the Footer**

In `landing/app/page.tsx`, just before `<Footer />`, add:

```tsx
      {/* ──── Hosted Waitlist Banner ──── */}
      <div className="py-6 px-6" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="max-w-4xl mx-auto flex flex-col sm:flex-row items-center justify-center gap-4">
          <p className="text-sm shrink-0" style={{ fontFamily: "'Space Mono', monospace", color: "var(--text-muted)" }}>
            Prefer not to self-host? We&apos;re building a managed version.
          </p>
          <WaitlistForm compact />
        </div>
      </div>
```

Re-add the WaitlistForm import at the top of `page.tsx` since the banner uses it:

```tsx
import WaitlistForm from "./waitlist-form";
```

(Actually, since we removed it in step 1 and re-add it here — net effect: keep the import.)

- [ ] **Step 3: Update the Footer component to include waitlist in footer**

In `landing/app/nav.tsx`, update the Footer component. Import WaitlistForm at the top of the file (add after the `"use client";` line):

```tsx
import WaitlistForm from "./waitlist-form";
```

Then replace the footer links array (lines 92-96) to remove the "Waitlist" link and add a "Hosted" label:

```tsx
          {[
            { label: "GitHub", href: GITHUB_URL, external: true },
            { label: "Docs", href: "https://docs.pingcrm.xyz/", external: true },
          ].map((link) => (
```

And add a compact waitlist form row below the existing footer content. Replace the entire Footer function (lines 86-124) with:

```tsx
export function Footer() {
  return (
    <footer className="py-12 px-6" style={{ borderTop: "1px solid var(--border)" }}>
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-6">
          <PingLogo />
          <div className="flex items-center gap-6">
            {[
              { label: "GitHub", href: GITHUB_URL, external: true },
              { label: "Docs", href: "https://docs.pingcrm.xyz/", external: true },
            ].map((link) => (
              <a
                key={link.label}
                href={link.href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs transition-colors duration-200 hover:!text-[var(--text)]"
                style={{ fontFamily: "'Space Mono', monospace", color: "var(--text-dim)" }}
              >
                {link.label}
              </a>
            ))}
          </div>
          <p className="text-xs" style={{ fontFamily: "'Space Mono', monospace", color: "var(--text-dim)" }}>
            Built by{" "}
            <a
              href="https://sawinyh.com"
              target="_blank"
              rel="noopener noreferrer"
              className="transition-colors duration-200 hover:!text-[var(--text)]"
              style={{ color: "var(--accent)", textDecoration: "none" }}
            >
              Sawinyh.com
            </a>
          </p>
        </div>
        <div className="mt-8 pt-6 flex flex-col sm:flex-row items-center justify-center gap-3" style={{ borderTop: "1px solid var(--border)" }}>
          <span className="text-xs shrink-0" style={{ fontFamily: "'Space Mono', monospace", color: "var(--text-dim)" }}>
            Hosted version coming soon
          </span>
          <WaitlistForm compact />
        </div>
      </div>
    </footer>
  );
}
```

- [ ] **Step 4: Verify build succeeds**

Run: `cd /Users/sneg55-pro13/Documents/github/pingcrm/landing && npm run build 2>&1 | tail -20`
Expected: Build succeeds with no errors.

- [ ] **Step 5: Commit**

```bash
git add landing/app/page.tsx landing/app/nav.tsx landing/app/waitlist-form.tsx
git commit -m "feat(landing): remove waitlist section, add compact banner and footer form"
```

---

### Task 6: Visual verification

- [ ] **Step 1: Run dev server and verify in browser**

Run: `cd /Users/sneg55-pro13/Documents/github/pingcrm/landing && npm run dev`

Use agent-browser to verify:
1. Hero has "Self-Host Now" + "Setup Guide" (no waitlist CTA)
2. Nav says "Get Started" (not "Get Early Access")
3. Open Source section shows "Deploy in under 10 minutes with Docker Compose." and both "Star on GitHub" + "Read the Docs" buttons
4. No dedicated waitlist section exists
5. Compact waitlist banner appears above footer
6. Footer contains inline waitlist form with "Hosted version coming soon" label
7. Compact waitlist form submits correctly (enter email, verify success state)

- [ ] **Step 2: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix(landing): visual polish from browser verification"
```
