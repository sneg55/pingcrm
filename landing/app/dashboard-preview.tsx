"use client";

import { useState, useEffect } from "react";

function Avatar({ initials, color }: { initials: string; color: string }) {
  return (
    <div
      className="w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0"
      style={{ background: color, color: "#fff", fontFamily: "'Space Mono', monospace" }}
    >
      {initials}
    </div>
  );
}

function StatCard({ icon, value, label }: { icon: React.ReactNode; value: string; label: string }) {
  return (
    <div
      className="rounded-lg px-4 py-3 flex-1 min-w-0"
      style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
    >
      <div className="mb-1.5 opacity-60">{icon}</div>
      <div className="text-xl font-bold" style={{ fontFamily: "'Space Mono', monospace", color: "var(--text)" }}>
        {value}
      </div>
      <div className="text-[10px]" style={{ color: "var(--text-dim)", fontFamily: "'Space Mono', monospace" }}>
        {label}
      </div>
    </div>
  );
}

/* ── Screen 1: Dashboard ── */
function DashboardScreen() {
  return (
    <div className="px-4 py-3">
      <div className="mb-3">
        <h3 className="text-sm font-bold" style={{ fontFamily: "'Space Mono', monospace", color: "var(--text)" }}>
          Dashboard
        </h3>
        <p className="text-[10px] mt-0.5" style={{ color: "var(--text-dim)", fontFamily: "'Space Mono', monospace" }}>
          You have <span style={{ color: "var(--accent)" }}>1 pending suggestion</span> and{" "}
          <span style={{ color: "var(--text)" }}>5 contacts</span> need attention.
        </p>
      </div>

      <div className="flex gap-2 mb-3">
        <StatCard
          icon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4-4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></svg>}
          value="4,967"
          label="Total contacts"
        />
        <StatCard
          icon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" /></svg>}
          value="360"
          label="Active relationships"
        />
        <StatCard
          icon={<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>}
          value="722"
          label="Interactions this week"
        />
      </div>

      <div className="flex gap-2">
        {/* Left: Pending Follow-ups + Recent Activity */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] font-bold" style={{ fontFamily: "'Space Mono', monospace", color: "var(--text)" }}>
              Pending Follow-ups
            </span>
            <span className="text-[9px]" style={{ fontFamily: "'Space Mono', monospace", color: "var(--accent)" }}>
              View all →
            </span>
          </div>

          <div className="rounded-lg p-2.5 mb-2" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
            <div className="flex items-center gap-2 mb-1.5">
              <Avatar initials="S" color="#2563eb" />
              <span className="text-[11px] font-bold" style={{ fontFamily: "'Space Mono', monospace", color: "var(--text)" }}>Sehaj</span>
              <span className="text-[9px] px-1.5 py-0.5 rounded-full" style={{ background: "rgba(239,68,68,0.15)", color: "#ef4444", fontFamily: "'Space Mono', monospace" }}>
                Cold (0)
              </span>
              <span className="text-[9px] ml-auto" style={{ color: "var(--text-dim)", fontFamily: "'Space Mono', monospace" }}>90+ days</span>
            </div>
            <p className="text-[10px] leading-relaxed" style={{ color: "var(--text-muted)", fontFamily: "'Space Mono', monospace" }}>
              Hey Sehaj, hope you&apos;ve been well! Just realized it&apos;s been way too long since we connected...
            </p>
          </div>

          <span className="text-[10px] font-bold block mb-1.5" style={{ fontFamily: "'Space Mono', monospace", color: "var(--text)" }}>
            Recent Activity
          </span>
          {[
            { initials: "A", color: "#0ea5e9", name: "Ali", msg: "Hey Ali! It's been a while since we connected about Assemble...", time: "2h ago" },
            { initials: "AK", color: "#8b5cf6", name: "Apurv Kaushal", msg: "Hey Apurv! It's been way too long since we chatted after...", time: "2h ago" },
          ].map((item) => (
            <div key={item.name} className="flex items-center gap-2 py-1.5" style={{ borderBottom: "1px solid var(--border)" }}>
              <Avatar initials={item.initials} color={item.color} />
              <div className="min-w-0 flex-1">
                <div className="text-[10px] font-bold" style={{ fontFamily: "'Space Mono', monospace", color: "var(--text)" }}>{item.name}</div>
                <div className="text-[9px] truncate" style={{ color: "var(--text-dim)", fontFamily: "'Space Mono', monospace" }}>{item.msg}</div>
              </div>
              <span className="text-[8px] shrink-0" style={{ color: "var(--text-dim)", fontFamily: "'Space Mono', monospace" }}>{item.time}</span>
            </div>
          ))}
        </div>

        {/* Right: Needs Attention */}
        <div className="w-[180px] shrink-0 rounded-lg p-2.5" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] font-bold" style={{ fontFamily: "'Space Mono', monospace", color: "var(--text)" }}>Needs Attention</span>
            <span className="text-[8px] px-1.5 py-0.5 rounded-full" style={{ background: "rgba(239,68,68,0.15)", color: "#ef4444", fontFamily: "'Space Mono', monospace" }}>5</span>
          </div>
          <p className="text-[8px] mb-2" style={{ color: "var(--text-dim)", fontFamily: "'Space Mono', monospace" }}>
            High-priority contacts going silent
          </p>
          {[
            { initials: "RF", name: "Roman Frank", days: "3153d" },
            { initials: "HP", name: "Henrik Pedersen", days: "3108d" },
            { initials: "OK", name: "Olha Kozynets", days: "3094d" },
            { initials: "MA", name: "Maxim A.", days: "3090d" },
            { initials: "VB", name: "Vladimir Bugay", days: "3090d" },
          ].map((item) => (
            <div key={item.initials} className="flex items-center gap-1.5 py-1" style={{ borderBottom: "1px solid var(--border)" }}>
              <Avatar initials={item.initials} color="#dc2626" />
              <div className="min-w-0 flex-1">
                <div className="text-[9px] truncate" style={{ fontFamily: "'Space Mono', monospace", color: "var(--text-muted)" }}>{item.name}</div>
              </div>
              <span className="text-[8px] shrink-0 flex items-center gap-0.5" style={{ color: "#ef4444", fontFamily: "'Space Mono', monospace" }}>
                <span className="w-1 h-1 rounded-full inline-block" style={{ background: "#ef4444" }} />
                {item.days}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Screen 2: Contact Detail ── */
function ContactScreen() {
  return (
    <div className="px-4 py-3">
      {/* Contact header */}
      <div className="flex items-center gap-3 mb-3 pb-3" style={{ borderBottom: "1px solid var(--border)" }}>
        <div
          className="w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
          style={{ background: "linear-gradient(135deg, #6366f1, #8b5cf6)", color: "#fff", fontFamily: "'Space Mono', monospace" }}
        >
          NR
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold" style={{ fontFamily: "'Space Mono', monospace", color: "var(--text)" }}>
              Nic RH
            </span>
            <span
              className="text-[8px] px-1.5 py-0.5 rounded-full"
              style={{ background: "rgba(239,68,68,0.15)", color: "#ef4444", fontFamily: "'Space Mono', monospace" }}
            >
              Cold
            </span>
          </div>
          <div className="text-[10px]" style={{ color: "var(--text-dim)", fontFamily: "'Space Mono', monospace" }}>
            Founder, CEO // X: @nic_builds
          </div>
        </div>
        <div className="flex gap-1">
          {["🔥", "⚡", "🔗"].map((icon, i) => (
            <div
              key={i}
              className="w-6 h-6 rounded flex items-center justify-center text-[10px]"
              style={{ border: "1px solid var(--border)", background: i === 1 ? "var(--accent-glow)" : "var(--bg-surface)" }}
            >
              {icon}
            </div>
          ))}
        </div>
      </div>

      <div className="flex gap-3">
        {/* Left: Contact Details */}
        <div className="w-[160px] shrink-0">
          <span className="text-[10px] font-bold block mb-2" style={{ fontFamily: "'Space Mono', monospace", color: "var(--text)" }}>
            Contact Details
          </span>
          {[
            { label: "Company", value: "Concrete", accent: true },
            { label: "Telegram", value: "nic_rh", accent: true },
            { label: "Twitter", value: "nic_builds", accent: true },
            { label: "Email", value: "—", accent: false },
            { label: "LinkedIn", value: "—", accent: false },
          ].map((field) => (
            <div key={field.label} className="flex justify-between py-1" style={{ borderBottom: "1px solid var(--border)" }}>
              <span className="text-[9px]" style={{ color: "var(--text-dim)", fontFamily: "'Space Mono', monospace" }}>{field.label}</span>
              <span
                className="text-[9px]"
                style={{ color: field.accent ? "var(--accent)" : "var(--text-dim)", fontFamily: "'Space Mono', monospace" }}
              >
                {field.value}
              </span>
            </div>
          ))}
        </div>

        {/* Right: Timeline */}
        <div className="flex-1 min-w-0">
          {/* Message composer hint */}
          <div
            className="rounded-lg px-3 py-2 mb-2 flex items-center gap-2"
            style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--text-dim)" strokeWidth="1.5">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
            <span className="text-[10px]" style={{ color: "var(--text-dim)", fontFamily: "'Space Mono', monospace" }}>
              Write a message...
            </span>
          </div>

          {/* Timeline messages */}
          <div className="space-y-2">
            <div className="text-center">
              <span className="text-[8px]" style={{ color: "var(--text-dim)", fontFamily: "'Space Mono', monospace" }}>TODAY</span>
            </div>

            {/* Outbound message */}
            <div className="flex justify-end">
              <div className="max-w-[85%]">
                <div
                  className="rounded-lg px-3 py-2 text-[10px] leading-relaxed"
                  style={{
                    background: "linear-gradient(135deg, var(--accent-dim), var(--accent))",
                    color: "var(--bg)",
                    fontFamily: "'Space Mono', monospace",
                  }}
                >
                  Hey Nic! Saw Concrete just crossed $1B TVL — that&apos;s incredible growth. How&apos;s everything going?
                </div>
                <div className="flex justify-end items-center gap-1 mt-0.5">
                  <span className="text-[8px]" style={{ color: "var(--text-dim)", fontFamily: "'Space Mono', monospace" }}>
                    4:33 PM · Telegram
                  </span>
                  <span className="text-[8px]" style={{ color: "var(--accent)", fontFamily: "'Space Mono', monospace" }}>You</span>
                </div>
              </div>
            </div>

            <div className="text-center">
              <span className="text-[8px]" style={{ color: "var(--text-dim)", fontFamily: "'Space Mono', monospace" }}>SEP 22, 2025</span>
            </div>

            {/* Older outbound */}
            <div className="flex justify-end">
              <div className="max-w-[85%]">
                <div
                  className="rounded-lg px-3 py-2 text-[10px] leading-relaxed"
                  style={{
                    background: "linear-gradient(135deg, var(--accent-dim), var(--accent))",
                    color: "var(--bg)",
                    fontFamily: "'Space Mono', monospace",
                  }}
                >
                  Are you going to Token2049 in Singapore? Would be awesome to catch up in person if you&apos;re around.
                </div>
                <div className="flex justify-end items-center gap-1 mt-0.5">
                  <span className="text-[8px]" style={{ color: "var(--text-dim)", fontFamily: "'Space Mono', monospace" }}>
                    9:39 AM · Telegram
                  </span>
                  <span className="text-[8px]" style={{ color: "var(--accent)", fontFamily: "'Space Mono', monospace" }}>You</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Screen 3: Suggestions with Message Editor ── */
function SuggestionsScreen() {
  const mono = "'Space Mono', monospace";
  return (
    <div className="px-4 py-3">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-bold" style={{ fontFamily: mono, color: "var(--text)" }}>
              Suggestions
            </h3>
            <span
              className="text-[9px] px-1.5 py-0.5 rounded-full font-bold"
              style={{ background: "var(--accent-glow)", color: "var(--accent)", fontFamily: mono }}
            >
              3 pending
            </span>
          </div>
          <p className="text-[10px] mt-0.5" style={{ color: "var(--text-dim)", fontFamily: mono }}>
            AI-suggested follow-ups for your network
          </p>
        </div>
        <div
          className="px-2 py-1 rounded text-[9px]"
          style={{ background: "var(--accent-glow)", border: "1px solid var(--accent-dim)", color: "var(--accent)", fontFamily: mono }}
        >
          Generate new
        </div>
      </div>

      {/* Expanded suggestion card with message editor */}
      <div
        className="rounded-lg p-3 mb-2"
        style={{ background: "var(--bg-surface)", border: "1px solid var(--accent-dim)" }}
      >
        {/* Card header */}
        <div className="flex items-center gap-2 mb-2">
          <Avatar initials="AR" color="#6366f1" />
          <span className="text-[11px] font-bold" style={{ fontFamily: mono, color: "var(--text)" }}>
            Alex Rivera
          </span>
          <span
            className="text-[9px] px-1.5 py-0.5 rounded-full"
            style={{ background: "rgba(245,158,11,0.15)", color: "#f59e0b", fontFamily: mono }}
          >
            Warm (5)
          </span>
          <span className="text-[9px] ml-auto" style={{ color: "var(--text-dim)", fontFamily: mono }}>
            45 days ago
          </span>
        </div>

        {/* Trigger pill */}
        <div className="flex items-center gap-1 mb-2">
          <span
            className="inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded-full"
            style={{ background: "rgba(59,130,246,0.15)", color: "#60a5fa", fontFamily: mono }}
          >
            <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
            </svg>
            Job change detected
          </span>
        </div>

        {/* Divider */}
        <div className="mb-2" style={{ borderTop: "1px solid var(--border)" }} />

        {/* Channel selector */}
        <div className="flex gap-1.5 mb-2">
          {[
            { label: "Email", active: false, color: "#3b82f6" },
            { label: "Telegram", active: true, color: "#0ea5e9" },
            { label: "Twitter", active: false, color: "#64748b" },
          ].map((ch) => (
            <div
              key={ch.label}
              className="px-2 py-0.5 rounded text-[9px]"
              style={{
                fontFamily: mono,
                background: ch.active ? `${ch.color}20` : "transparent",
                border: `1px solid ${ch.active ? ch.color : "var(--border)"}`,
                color: ch.active ? ch.color : "var(--text-dim)",
              }}
            >
              {ch.label}
            </div>
          ))}
        </div>

        {/* Message textarea */}
        <div
          className="rounded-lg p-2.5 mb-2"
          style={{ background: "var(--bg)", border: "1px solid var(--border)" }}
        >
          <p className="text-[10px] leading-[1.6]" style={{ color: "var(--text)", fontFamily: mono }}>
            Hey Alex! Just saw you moved to Stripe — congrats on the new role! VP Engineering is a huge step. Would love to catch up and hear how the transition&apos;s going. Free for a quick call this week?
          </p>
          <div className="flex justify-end mt-1.5">
            <span className="text-[8px]" style={{ color: "var(--text-dim)", fontFamily: mono }}>
              186/4096
            </span>
          </div>
        </div>

        {/* Actions row */}
        <div className="flex items-center justify-between">
          <div className="flex gap-1.5">
            {/* Snooze */}
            <div
              className="px-2 py-0.5 rounded text-[9px] flex items-center gap-1"
              style={{ border: "1px solid rgba(245,158,11,0.3)", color: "#f59e0b", fontFamily: mono }}
            >
              <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
              </svg>
              Snooze
            </div>
            {/* Dismiss */}
            <div
              className="px-2 py-0.5 rounded text-[9px] flex items-center gap-1"
              style={{ border: "1px solid var(--border)", color: "var(--text-dim)", fontFamily: mono }}
            >
              <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
              Dismiss
            </div>
            {/* Regenerate */}
            <div
              className="px-2 py-0.5 rounded text-[9px] flex items-center gap-1"
              style={{ border: "1px solid var(--border)", color: "var(--text-muted)", fontFamily: mono }}
            >
              <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="23 4 23 10 17 10" /><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
              </svg>
              Regenerate
            </div>
          </div>
          {/* Send */}
          <div
            className="px-3 py-1 rounded text-[9px] font-bold flex items-center gap-1"
            style={{
              background: "linear-gradient(135deg, var(--accent-dim), var(--accent))",
              color: "var(--bg)",
              fontFamily: mono,
            }}
          >
            <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
            Send
          </div>
        </div>
      </div>

      {/* Collapsed suggestion cards */}
      {[
        { initials: "SC", color: "#ec4899", name: "Sarah Chen", badge: "Strong (8)", badgeColor: "#10b981", trigger: "Replied to your tweet, no DM in 90d", days: "92 days ago", msg: "Hey Sarah! I noticed your reply about the API design patterns thread — great insights..." },
        { initials: "MJ", color: "#f97316", name: "Marcus Johnson", badge: "Warm (4)", badgeColor: "#f59e0b", trigger: "Fundraising signal detected", days: "60 days ago", msg: "Marcus, congrats on the seed round! Saw the announcement and wanted to reach out..." },
      ].map((s) => (
        <div
          key={s.initials}
          className="rounded-lg p-2.5 mb-2"
          style={{ background: "var(--bg-surface)", border: "1px solid var(--border)" }}
        >
          <div className="flex items-center gap-2 mb-1">
            <Avatar initials={s.initials} color={s.color} />
            <span className="text-[11px] font-bold" style={{ fontFamily: mono, color: "var(--text)" }}>{s.name}</span>
            <span
              className="text-[9px] px-1.5 py-0.5 rounded-full"
              style={{ background: `${s.badgeColor}20`, color: s.badgeColor, fontFamily: mono }}
            >
              {s.badge}
            </span>
            <span className="text-[9px] ml-auto" style={{ color: "var(--text-dim)", fontFamily: mono }}>{s.days}</span>
          </div>
          <p className="text-[9px] truncate" style={{ color: "var(--text-dim)", fontFamily: mono }}>{s.msg}</p>
        </div>
      ))}
    </div>
  );
}

/* ── Nav bar (shared) ── */
function MiniNav({ activeScreen }: { activeScreen: number }) {
  return (
    <div
      className="flex items-center gap-4 px-4 py-2"
      style={{ borderBottom: "1px solid var(--border)", background: "var(--bg)" }}
    >
      <div className="flex items-center gap-1.5">
        <div className="glow-dot" style={{ width: "5px", height: "5px" }} />
        <span className="text-xs font-bold" style={{ fontFamily: "'Space Mono', monospace", color: "var(--accent)" }}>
          Ping
        </span>
      </div>
      <div className="flex gap-3">
        {["Dashboard", "Suggestions", "Contacts", "Orgs"].map((item, i) => {
          const isActive = (activeScreen === 0 && i === 0) || (activeScreen === 1 && i === 2) || (activeScreen === 2 && i === 1);
          return (
            <span
              key={item}
              className="text-[10px]"
              style={{
                fontFamily: "'Space Mono', monospace",
                color: isActive ? "var(--accent)" : "var(--text-dim)",
                paddingBottom: isActive ? "1px" : undefined,
                borderBottom: isActive ? "1px solid var(--accent)" : undefined,
              }}
            >
              {item}
            </span>
          );
        })}
      </div>
      <div className="ml-auto flex items-center gap-2">
        <div className="relative">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--text-dim)" strokeWidth="2">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          </svg>
          <div className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full" style={{ background: "var(--accent)" }} />
        </div>
        <span className="text-[10px]" style={{ fontFamily: "'Space Mono', monospace", color: "var(--text-dim)" }}>
          Nick S.
        </span>
      </div>
    </div>
  );
}

/* ── Main component with screen switching ── */
export default function DashboardPreview() {
  const [activeScreen, setActiveScreen] = useState(0);
  const [fading, setFading] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      setFading(true);
      setTimeout(() => {
        setActiveScreen((s) => (s + 1) % 3);
        setFading(false);
      }, 400);
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      <div
        className="rounded-xl overflow-hidden"
        style={{
          border: "1px solid var(--border)",
          background: "var(--bg-elevated)",
          boxShadow: "0 0 60px rgba(52, 211, 153, 0.06), 0 24px 48px rgba(0,0,0,0.4)",
        }}
      >
        <MiniNav activeScreen={activeScreen} />
        <div
          style={{
            opacity: fading ? 0 : 1,
            transition: "opacity 0.4s ease-in-out",
          }}
        >
          {activeScreen === 0 ? <DashboardScreen /> : activeScreen === 1 ? <ContactScreen /> : <SuggestionsScreen />}
        </div>
      </div>

      {/* Screen indicator dots */}
      <div className="flex justify-center gap-2 mt-4">
        {[0, 1, 2].map((i) => (
          <button
            key={i}
            onClick={() => {
              if (i !== activeScreen) {
                setFading(true);
                setTimeout(() => {
                  setActiveScreen(i);
                  setFading(false);
                }, 400);
              }
            }}
            className="w-2 h-2 rounded-full transition-all duration-300"
            style={{
              background: activeScreen === i ? "var(--accent)" : "var(--border-bright)",
              boxShadow: activeScreen === i ? "0 0 8px var(--accent-glow-strong)" : "none",
            }}
          />
        ))}
      </div>
    </div>
  );
}
