"use client";

import { useState, type FormEvent } from "react";

export default function WaitlistForm({ compact = false }: { compact?: boolean }) {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [message, setMessage] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!email) return;

    setStatus("loading");

    const formId = process.env.NEXT_PUBLIC_LOOPS_FORM_ID;
    if (!formId) {
      setStatus("error");
      setMessage("Waitlist not configured.");
      return;
    }

    try {
      const formBody = `email=${encodeURIComponent(email)}`;
      const res = await fetch(`https://app.loops.so/api/newsletter-form/${formId}`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formBody,
      });

      if (res.ok) {
        setStatus("success");
        setMessage("You're on the list. We'll be in touch.");
        setEmail("");
      } else {
        setStatus("error");
        setMessage("Something went wrong. Try again.");
      }
    } catch {
      setStatus("error");
      setMessage("Network error. Try again.");
    }
  }

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
}
