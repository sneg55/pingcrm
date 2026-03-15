"use client";

import { useState, memo } from "react";
import { Building2 } from "lucide-react";

const COMMON_DOMAINS = new Set([
  "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
  "icloud.com", "mail.com", "protonmail.com", "aol.com",
  "live.com", "me.com", "msn.com", "yandex.com",
]);

/** Extract a company domain from an email list (skips common providers). */
function domainFromEmails(emails: string[] | null | undefined): string | null {
  if (!emails?.length) return null;
  for (const email of emails) {
    const domain = email.split("@")[1]?.toLowerCase();
    if (domain && !COMMON_DOMAINS.has(domain)) return domain;
  }
  return null;
}

interface CompanyFaviconProps {
  /** Organization logo URL (takes priority over all fallbacks). */
  logoUrl?: string | null;
  /** Organization domain (used for favicon.ico fallback when logoUrl absent). */
  domain?: string | null;
  /** Contact emails — domain is derived from the first non-common email. */
  emails?: string[] | null;
  /** Icon size class (default: "w-4 h-4"). */
  size?: string;
  /** Additional CSS classes on the wrapper. */
  className?: string;
}

export const CompanyFavicon = memo(function CompanyFavicon({
  logoUrl,
  domain,
  emails,
  size = "w-4 h-4",
  className,
}: CompanyFaviconProps) {
  const [logFailed, setLogFailed] = useState(false);
  const [favFailed, setFavFailed] = useState(false);

  // Priority 1: explicit logo URL from org record
  if (logoUrl && !logFailed) {
    return (
      <img
        src={logoUrl}
        alt=""
        className={`${size} rounded-sm object-contain ${className ?? ""}`}
        onError={() => setLogFailed(true)}
      />
    );
  }

  // Priority 2: derive domain and attempt favicon.ico directly
  const resolvedDomain = domain || domainFromEmails(emails);
  if (resolvedDomain && !favFailed) {
    return (
      <img
        src={`https://${resolvedDomain}/favicon.ico`}
        alt=""
        className={`${size} rounded-sm ${className ?? ""}`}
        onError={() => setFavFailed(true)}
      />
    );
  }

  // Priority 3: Building2 placeholder
  return <Building2 className={`${size} text-zinc-400 ${className ?? ""}`} />;
});

export { domainFromEmails };
