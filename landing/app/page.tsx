import WaitlistForm from "./waitlist-form";
import DashboardPreview from "./dashboard-preview";
import { Nav, Footer } from "./nav";
import ScrollRevealInit from "./scroll-reveal-init";

const GITHUB_URL = "https://github.com/sneg55/pingcrm";

const FEATURES = [
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2L2 7l10 5 10-5-10-5z" />
        <path d="M2 17l10 5 10-5" />
        <path d="M2 12l10 5 10-5" />
      </svg>
    ),
    title: "Multi-Platform Sync",
    description:
      "Connect Gmail, Telegram, Twitter/X, and LinkedIn. Every conversation, every DM, every thread — unified into one timeline per contact.",
  },
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
        <path d="M8 10h.01M12 10h.01M16 10h.01" />
      </svg>
    ),
    title: "AI Follow-Up Drafts",
    description:
      "Claude writes contextual messages based on your history. One click to edit, one click to send. No more staring at blank compose windows.",
  },
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
      </svg>
    ),
    title: "Relationship Scoring",
    description:
      "A transparent 0\u201310 score decomposed into reciprocity, recency, frequency, and breadth. See exactly why a relationship is cooling off.",
  },
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <polyline points="12 6 12 12 16 14" />
      </svg>
    ),
    title: "Unified Timeline",
    description:
      "Every touchpoint with a contact — emails, DMs, group chats, mentions — in chronological order. Full context at a glance.",
  },
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4-4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M22 21v-2a4 4 0 00-3-3.87" />
        <path d="M16 3.13a4 4 0 010 7.75" />
      </svg>
    ),
    title: "Identity Resolution",
    description:
      "Automatically merges alex@startup.com, @alexbuilds on Twitter, Alex R. on LinkedIn, and @alexr on Telegram into one unified profile.",
  },
  {
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
        <line x1="16" y1="2" x2="16" y2="6" />
        <line x1="8" y1="2" x2="8" y2="6" />
        <line x1="3" y1="10" x2="21" y2="10" />
        <path d="M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01" />
      </svg>
    ),
    title: "Weekly Digest",
    description:
      "Every week: 3\u20135 people worth reaching out to, and why. Bio changes, job moves, long silences — nothing slips through. Need more? Ask Ping to surface additional contacts anytime.",
  },
];

const STEPS = [
  {
    number: "01",
    label: "Connect",
    description: "Link your Gmail, Telegram, Twitter, and LinkedIn accounts. Import contacts via CSV or Google Contacts.",
    visual: (
      <div className="flex gap-3 items-center justify-center">
        {["Gmail", "Telegram", "Twitter", "LinkedIn"].map((p) => (
          <span
            key={p}
            className="px-3 py-1.5 rounded text-xs tracking-wider"
            style={{
              fontFamily: "'Space Mono', monospace",
              background: "var(--accent-glow)",
              border: "1px solid var(--accent-dim)",
              color: "var(--accent)",
            }}
          >
            {p}
          </span>
        ))}
      </div>
    ),
  },
  {
    number: "02",
    label: "Monitor",
    description: "Ping organizes your conversations, surfaces patterns, and flags when relationships need attention.",
    visual: (
      <div className="flex items-end gap-1 justify-center h-10">
        {[3, 7, 5, 2, 6, 8, 4].map((h, i) => (
          <div
            key={i}
            className="w-3 rounded-sm"
            style={{
              height: `${h * 4}px`,
              background: "linear-gradient(to top, var(--accent-dim), var(--accent))",
              opacity: 0.4 + (h / 8) * 0.6,
            }}
          />
        ))}
      </div>
    ),
  },
  {
    number: "03",
    label: "Act",
    description: "Get a weekly digest with AI-drafted messages. Review, tweak, and send — staying in touch without the mental overhead.",
    visual: (
      <div
        className="px-4 py-2 rounded text-xs text-center"
        style={{
          fontFamily: "'Space Mono', monospace",
          background: "var(--bg-surface)",
          border: "1px solid var(--border-bright)",
          color: "var(--text-muted)",
        }}
      >
        <span style={{ color: "var(--accent)" }}>AI:</span>{" "}
        &quot;Hey Alex, saw you just raised...&quot;
      </div>
    ),
  },
];

function GitHubIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
    </svg>
  );
}

export default function LandingPage() {
  return (
    <div className="relative overflow-hidden">
      <ScrollRevealInit />
      <Nav />

      {/* ──── Hero ──── */}
      <section className="relative pt-32 pb-24 px-6">
        <div className="absolute inset-0 grid-bg grid-bg-fade opacity-40" />
        <div
          className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[600px] rounded-full"
          style={{ background: "radial-gradient(ellipse, var(--accent-glow) 0%, transparent 70%)" }}
        />

        <div className="relative max-w-4xl mx-auto text-center">
          <div className="animate-fade-up delay-1 inline-flex items-center gap-2 px-3 py-1 rounded-full mb-8"
            style={{ border: "1px solid var(--border-bright)", background: "var(--bg-elevated)" }}>
            <div className="glow-dot" style={{ width: "4px", height: "4px" }} />
            <span style={{ fontFamily: "'Space Mono', monospace", fontSize: "12px", color: "var(--text-muted)", letterSpacing: "0.05em" }}>
              OPEN SOURCE &middot; SELF-HOSTABLE
            </span>
          </div>

          <h1
            className="animate-fade-up delay-2 text-5xl sm:text-6xl md:text-7xl font-bold leading-[1.05] tracking-tight mb-6"
            style={{ fontFamily: "'Space Mono', monospace" }}
          >
            Your network is{" "}
            <span
              className="relative inline-block"
              style={{
                background: "linear-gradient(135deg, var(--accent), #6ee7b7)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              decaying
            </span>
            <br />
            <span className="text-4xl sm:text-5xl md:text-6xl" style={{ color: "var(--text-muted)", fontWeight: 400 }}>
              Ping fixes that.
            </span>
          </h1>

          <p
            className="animate-fade-up delay-3 text-lg sm:text-xl leading-relaxed max-w-2xl mx-auto mb-10"
            style={{ color: "var(--text-muted)", fontFamily: "'Newsreader', Georgia, serif" }}
          >
            Ping watches your relationships across Gmail, Telegram, Twitter, and LinkedIn — tells you{" "}
            <em style={{ color: "var(--text)", fontStyle: "italic" }}>who&apos;s slipping away</em>, and{" "}
            <em style={{ color: "var(--text)", fontStyle: "italic" }}>writes the message</em> to bring them back.
          </p>

          <div className="animate-fade-up delay-4 flex flex-col sm:flex-row gap-4 justify-center items-center">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2.5 px-6 py-3 rounded-lg text-sm font-bold tracking-wide transition-all duration-200 hover:shadow-[0_0_24px_var(--accent-glow-strong)] hover:-translate-y-0.5"
              style={{
                fontFamily: "'Space Mono', monospace",
                background: "linear-gradient(135deg, var(--accent-dim), var(--accent))",
                color: "var(--bg)",
                fontSize: "14px",
              }}
            >
              <GitHubIcon size={18} />
              Self-Host Now
            </a>
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
          </div>

          {/* Dashboard preview */}
          <div className="animate-fade-up delay-5 mt-16 max-w-2xl mx-auto">
            <DashboardPreview />
          </div>
        </div>
      </section>

      <div className="glow-line mx-auto max-w-4xl" />

      {/* ──── Features ──── */}
      <section className="scroll-reveal py-24 px-6">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <p
              className="text-xs tracking-[0.2em] uppercase mb-3"
              style={{ fontFamily: "'Space Mono', monospace", color: "var(--accent)" }}
            >
              What Ping Does
            </p>
            <h2
              className="text-3xl sm:text-4xl font-bold tracking-tight"
              style={{ fontFamily: "'Space Mono', monospace" }}
            >
              Six ways Ping keeps your{" "}
              <span style={{ color: "var(--accent)" }}>network alive</span>
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {FEATURES.map((feature) => (
              <div key={feature.title} className="feature-card rounded-xl p-6">
                <div className="mb-4 opacity-80">{feature.icon}</div>
                <h3
                  className="text-base font-bold mb-2 tracking-tight"
                  style={{ fontFamily: "'Space Mono', monospace" }}
                >
                  {feature.title}
                </h3>
                <p className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ──── How It Works ──── */}
      <section className="scroll-reveal py-24 px-6" style={{ background: "var(--bg-elevated)" }}>
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <p
              className="text-xs tracking-[0.2em] uppercase mb-3"
              style={{ fontFamily: "'Space Mono', monospace", color: "var(--accent)" }}
            >
              How It Works
            </p>
            <h2
              className="text-3xl sm:text-4xl font-bold tracking-tight"
              style={{ fontFamily: "'Space Mono', monospace" }}
            >
              Three steps to{" "}
              <span style={{ color: "var(--accent)" }}>effortless follow-up</span>
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 md:gap-6">
            {STEPS.map((step, i) => (
              <div key={step.number} className="relative text-center">
                <div
                  className="inline-flex items-center justify-center w-12 h-12 rounded-full mb-5"
                  style={{
                    border: "1px solid var(--accent-dim)",
                    background: "var(--accent-glow)",
                    fontFamily: "'Space Mono', monospace",
                    fontSize: "14px",
                    color: "var(--accent)",
                    fontWeight: 700,
                  }}
                >
                  {step.number}
                </div>

                {i < STEPS.length - 1 && (
                  <div
                    className="hidden md:block absolute top-6 left-[60%] w-[80%] h-px"
                    style={{
                      background: "linear-gradient(90deg, var(--accent-dim), transparent)",
                      opacity: 0.3,
                    }}
                  />
                )}

                <h3
                  className="text-xl font-bold mb-2 tracking-tight"
                  style={{ fontFamily: "'Space Mono', monospace" }}
                >
                  {step.label}
                </h3>
                <p className="text-sm leading-relaxed mb-5 max-w-xs mx-auto" style={{ color: "var(--text-muted)" }}>
                  {step.description}
                </p>
                <div>{step.visual}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ──── Open Source ──── */}
      <section className="scroll-reveal py-24 px-6 relative">
        <div className="absolute inset-0 grid-bg grid-bg-fade opacity-20" />
        <div className="relative max-w-3xl mx-auto text-center">
          <div className="inline-flex mb-6">
            <GitHubIcon size={48} />
          </div>
          <h2
            className="text-3xl sm:text-4xl font-bold tracking-tight mb-4"
            style={{ fontFamily: "'Space Mono', monospace" }}
          >
            Open source.{" "}
            <span style={{ color: "var(--accent)" }}>Your data, your server.</span>
          </h2>
          <p className="text-lg leading-relaxed mb-3 max-w-xl mx-auto" style={{ color: "var(--text-muted)" }}>
            PingCRM is fully open source. Self-host on your own infrastructure, audit every line of code, and own your relationship data completely.
            No vendor lock-in, no data harvesting.
          </p>
          <p className="text-sm mb-8" style={{ color: "var(--accent)", fontFamily: "'Space Mono', monospace" }}>
            Deploy in under 10 minutes with Docker Compose.
          </p>

          <div className="flex flex-wrap justify-center gap-2 mb-10">
            {["Python", "FastAPI", "Next.js", "PostgreSQL", "Redis", "Claude AI"].map((tech) => (
              <span
                key={tech}
                className="px-3 py-1 rounded text-xs"
                style={{
                  fontFamily: "'Space Mono', monospace",
                  background: "var(--bg-surface)",
                  border: "1px solid var(--border)",
                  color: "var(--text-muted)",
                  fontSize: "12px",
                }}
              >
                {tech}
              </span>
            ))}
          </div>

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
        </div>
      </section>

      {/* ──── Hosted Waitlist Banner ──── */}
      <div className="py-6 px-6" style={{ borderTop: "1px solid var(--border)" }}>
        <div className="max-w-4xl mx-auto flex flex-col sm:flex-row items-center justify-center gap-4">
          <p className="text-sm shrink-0" style={{ fontFamily: "'Space Mono', monospace", color: "var(--text-muted)" }}>
            Prefer not to self-host? We&apos;re building a managed version.
          </p>
          <WaitlistForm compact />
        </div>
      </div>

      <Footer />
    </div>
  );
}
