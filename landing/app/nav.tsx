"use client";

const GITHUB_URL = "https://github.com/sneg55/pingcrm";

function GitHubIcon({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
    </svg>
  );
}

function PingLogo() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="relative">
        <div className="glow-dot" />
        <div
          className="absolute inset-0 rounded-full animate-pulse-glow"
          style={{
            width: "18px",
            height: "18px",
            top: "-6px",
            left: "-6px",
            border: "1px solid var(--accent)",
            opacity: 0.3,
          }}
        />
      </div>
      <span
        className="text-lg font-bold tracking-tight"
        style={{ fontFamily: "'Space Mono', monospace", color: "var(--text)" }}
      >
        Ping<span style={{ color: "var(--accent)" }}>CRM</span>
      </span>
    </div>
  );
}

export function Nav() {
  return (
    <nav
      className="fixed top-0 left-0 right-0 z-50 backdrop-blur-md"
      style={{ background: "rgba(7,9,11,0.8)", borderBottom: "1px solid var(--border)" }}
    >
      <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
        <PingLogo />
        <div className="flex items-center gap-6">
          <a
            href="https://docs.pingcrm.xyz/"
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm transition-colors duration-200 hover:!text-[var(--text)]"
            style={{ fontFamily: "'Space Mono', monospace", color: "var(--text-muted)", fontSize: "13px" }}
          >
            Docs
          </a>
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 text-sm transition-colors duration-200 hover:!text-[var(--text)]"
            style={{ fontFamily: "'Space Mono', monospace", color: "var(--text-muted)", fontSize: "13px" }}
          >
            <GitHubIcon size={16} />
            Star
          </a>
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
        </div>
      </div>
    </nav>
  );
}

export function Footer() {
  return (
    <footer className="py-12 px-6" style={{ borderTop: "1px solid var(--border)" }}>
      <div className="max-w-6xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-6">
        <PingLogo />
        <div className="flex items-center gap-6">
          {[
            { label: "GitHub", href: GITHUB_URL, external: true },
            { label: "Docs", href: "https://docs.pingcrm.xyz/", external: true },
            { label: "Waitlist", href: "#waitlist", external: false },
          ].map((link) => (
            <a
              key={link.label}
              href={link.href}
              target={link.external ? "_blank" : undefined}
              rel={link.external ? "noopener noreferrer" : undefined}
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
    </footer>
  );
}
