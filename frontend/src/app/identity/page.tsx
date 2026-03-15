"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Mail,
  Twitter,
  MessageCircle,
  Building2,
  ScanSearch,
  GitMerge,
  X,
  Phone,
  Briefcase,
  Tag,
  FileText,
  Globe,
  ChevronDown,
  ChevronUp,
  CheckCircle,
  AlertCircle,
  HelpCircle,
  Check,
  BarChart2,
  Zap,
  CheckCircle2,
} from "lucide-react";
import {
  useIdentityMatches,
  useMergeMatch,
  useRejectMatch,
  useScanIdentity,
  type IdentityMatchContact,
  type IdentityMatch,
} from "@/hooks/use-identity";
import { cn } from "@/lib/utils";
import { ContactAvatar } from "@/components/contact-avatar";

/* ── Match type config ── */
interface MatchTypeStyle {
  label: string;
  icon: React.ReactNode;
  pillColors: string;
  barColor: string;
}

function matchTypeStyle(method: string, score: number): MatchTypeStyle {
  if (method === "deterministic" || score >= 0.85) {
    return {
      label: "Exact match",
      icon: <CheckCircle className="w-3.5 h-3.5" />,
      pillColors: "bg-emerald-50 text-emerald-700 border-emerald-200",
      barColor: "bg-emerald-500",
    };
  }
  if (method === "probabilistic" && score < 0.65) {
    return {
      label: "Probabilistic",
      icon: <HelpCircle className="w-3.5 h-3.5" />,
      pillColors: "bg-sky-50 text-sky-700 border-sky-200",
      barColor: "bg-sky-400",
    };
  }
  return {
    label: "Possible match",
    icon: <AlertCircle className="w-3.5 h-3.5" />,
    pillColors: "bg-amber-50 text-amber-700 border-amber-200",
    barColor: "bg-amber-400",
  };
}

/* ═══════════════ CONTACT PANEL ═══════════════ */

function ContactPanel({ contact }: { contact: IdentityMatchContact }) {
  const [expanded, setExpanded] = useState(false);
  const displayName = contact.full_name ?? "Unnamed";
  const primaryEmail = contact.emails[0] ?? null;
  const extraEmails = contact.emails.slice(1);

  const hasExtra =
    extraEmails.length > 0 ||
    contact.phones.length > 0 ||
    contact.title ||
    contact.linkedin_url ||
    contact.tags.length > 0 ||
    contact.notes ||
    contact.source;

  return (
    <div className="bg-stone-50 rounded-lg p-4 border border-stone-100">
      {/* Avatar + name */}
      <div className="flex items-center gap-3 mb-3">
        <ContactAvatar avatarUrl={null} name={displayName} size="sm" />
        <div className="min-w-0 flex-1">
          <Link
            href={`/contacts/${contact.id}`}
            className="text-sm font-semibold text-stone-900 hover:text-teal-700 transition-colors truncate block"
            onClick={(e) => e.stopPropagation()}
          >
            {displayName}
          </Link>
          {contact.source && (
            <p className="text-xs text-stone-400">
              Added via {contact.source}
            </p>
          )}
        </div>
      </div>

      <div className="space-y-1.5 text-xs text-stone-600">
        {contact.company && (
          <div className="flex items-center gap-2">
            <Building2 className="w-3.5 h-3.5 text-stone-400 shrink-0" />
            <span>{contact.company}</span>
          </div>
        )}
        {primaryEmail && (
          <div className="flex items-center gap-2">
            <Mail className="w-3.5 h-3.5 text-stone-400 shrink-0" />
            <span className="font-mono truncate">{primaryEmail}</span>
          </div>
        )}
        {contact.twitter_handle ? (
          <div className="flex items-center gap-2">
            <Twitter className="w-3.5 h-3.5 text-stone-400 shrink-0" />
            <span className="font-mono">@{contact.twitter_handle}</span>
          </div>
        ) : null}
        {contact.telegram_username ? (
          <div className="flex items-center gap-2">
            <MessageCircle className="w-3.5 h-3.5 text-stone-400 shrink-0" />
            <span className="font-mono">@{contact.telegram_username}</span>
          </div>
        ) : null}
      </div>

      {/* Expand toggle */}
      {hasExtra && (
        <>
          <button
            onClick={() => setExpanded(!expanded)}
            className="mt-3 text-xs text-teal-600 hover:text-teal-800 transition-colors flex items-center gap-1"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {expanded ? "Less" : "More details"}
          </button>

          {expanded && (
            <div className="mt-2 pt-2 border-t border-stone-200 space-y-1.5 text-xs text-stone-600">
              {contact.title && (
                <div className="flex items-center gap-2">
                  <Briefcase className="w-3.5 h-3.5 text-stone-400 shrink-0" />
                  <span className="truncate">{contact.title}</span>
                </div>
              )}
              {extraEmails.map((email) => (
                <div key={email} className="flex items-center gap-2 truncate">
                  <Mail className="w-3.5 h-3.5 text-stone-400 shrink-0" />
                  <span className="font-mono truncate">{email}</span>
                </div>
              ))}
              {contact.phones.map((phone) => (
                <div key={phone} className="flex items-center gap-2">
                  <Phone className="w-3.5 h-3.5 text-stone-400 shrink-0" />
                  <span className="font-mono">{phone}</span>
                </div>
              ))}
              {contact.linkedin_url && (
                <div className="flex items-center gap-2 truncate">
                  <Globe className="w-3.5 h-3.5 text-stone-400 shrink-0" />
                  <a href={contact.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-teal-600 hover:underline font-mono truncate">
                    LinkedIn
                  </a>
                </div>
              )}
              {contact.tags.length > 0 && (
                <div className="flex items-start gap-2">
                  <Tag className="w-3.5 h-3.5 text-stone-400 shrink-0 mt-0.5" />
                  <div className="flex flex-wrap gap-1">
                    {contact.tags.map((tag) => (
                      <span key={tag} className="px-1.5 py-0.5 rounded text-xs bg-stone-200 text-stone-700">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {contact.notes && (
                <div className="flex items-start gap-2">
                  <FileText className="w-3.5 h-3.5 text-stone-400 shrink-0 mt-0.5" />
                  <span className="text-xs text-stone-500 line-clamp-3">{contact.notes}</span>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ═══════════════ MATCH CARD ═══════════════ */

function MatchCard({
  match,
  onMerge,
  onReject,
  merging,
  rejecting,
}: {
  match: IdentityMatch;
  onMerge: () => void;
  onReject: () => void;
  merging: boolean;
  rejecting: boolean;
}) {
  const [breakdownOpen, setBreakdownOpen] = useState(false);
  const score = match.match_score ?? 0;
  const pct = Math.round(score * 100);
  const style = matchTypeStyle(match.match_method, score);
  const isAutoMergeReady = score >= 0.95;
  const isLowConfidence = score < 0.65;

  return (
    <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
      <div className="p-5">
        {/* Card header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3 flex-wrap">
            <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border", style.pillColors)}>
              {style.icon}
              {style.label}
            </span>
            <div className="flex items-center gap-2">
              <span className="text-sm font-mono font-medium text-stone-700">{pct}% match</span>
              <div className="w-24 h-1.5 bg-stone-100 rounded-full overflow-hidden">
                <div className={cn("h-full rounded-full", style.barColor)} style={{ width: `${pct}%` }} />
              </div>
            </div>
            {isAutoMergeReady && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-teal-50 text-teal-700 border border-teal-200">
                <Zap className="w-3 h-3" />
                Auto-merge ready
              </span>
            )}
          </div>
          <button
            onClick={() => setBreakdownOpen((v) => !v)}
            className="text-xs text-stone-400 hover:text-stone-600 transition-colors flex items-center gap-1"
          >
            <BarChart2 className="w-3.5 h-3.5" />
            Match detail
          </button>
        </div>

        {/* Match breakdown (expandable) */}
        {breakdownOpen && (
          <div className="mb-4">
            <div className="bg-stone-50 rounded-lg p-4 border border-stone-100">
              <p className="text-xs font-medium text-stone-500 mb-3 uppercase tracking-wide">Match breakdown</p>
              <div className="space-y-2.5">
                {[
                  { label: "Email domain", weight: 40 },
                  { label: "Name similarity", weight: 20 },
                  { label: "Same company", weight: 20 },
                  { label: "Username", weight: 10 },
                  { label: "Mutual signals", weight: 10 },
                ].map((item) => {
                  const contribution = Math.round(item.weight * score);
                  const hasMatch = contribution > 0;
                  return (
                    <div key={item.label} className="flex items-center gap-3">
                      {hasMatch ? (
                        <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                      ) : (
                        <X className="w-4 h-4 text-red-400 shrink-0" />
                      )}
                      <span className="text-xs text-stone-600 w-32 shrink-0">{item.label}</span>
                      <div className="flex-1 h-1.5 bg-stone-200 rounded-full overflow-hidden">
                        <div
                          className={cn("h-full rounded-full", hasMatch ? style.barColor : "bg-stone-300")}
                          style={{ width: `${contribution}%` }}
                        />
                      </div>
                      <span className="text-xs font-mono text-stone-400 w-8 text-right">{contribution}%</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* Side-by-side comparison */}
        <div className="grid grid-cols-[1fr_auto_1fr] gap-4 items-stretch">
          <ContactPanel contact={match.contact_a as IdentityMatchContact} />
          {/* VS divider */}
          <div className="flex items-center justify-center">
            <div className="flex flex-col items-center gap-1">
              <div className="w-px h-8 bg-stone-200" />
              <span className="text-xs font-mono font-medium text-stone-400 bg-stone-100 rounded px-1.5 py-0.5">vs</span>
              <div className="w-px h-8 bg-stone-200" />
            </div>
          </div>
          <ContactPanel contact={match.contact_b as IdentityMatchContact} />
        </div>
      </div>

      {/* Action footer */}
      <div className="px-5 py-3 border-t border-stone-100 bg-stone-50 flex items-center justify-between">
        {isLowConfidence && (
          <p className="text-xs text-stone-400">Low confidence — manual review recommended</p>
        )}
        <div className={cn("flex items-center gap-2", !isLowConfidence && "ml-auto")}>
          <button
            onClick={onReject}
            disabled={rejecting}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-stone-600 border border-stone-200 hover:bg-stone-100 disabled:opacity-50 transition-colors"
          >
            <X className="w-3.5 h-3.5" /> Not the same
          </button>
          <button
            onClick={onMerge}
            disabled={merging}
            className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-teal-600 text-white hover:bg-teal-700 disabled:opacity-50 transition-colors shadow-sm"
          >
            <GitMerge className="w-3.5 h-3.5" /> Merge
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════ TOAST ═══════════════ */

function Toast({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <div className="fixed bottom-6 right-6 z-50">
      <div
        className="flex items-center gap-3 bg-stone-900 text-white text-sm px-4 py-3 rounded-xl shadow-xl border border-stone-700 cursor-pointer"
        onClick={onDismiss}
      >
        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
        <span>{message}</span>
      </div>
    </div>
  );
}

/* ═══════════════ PAGE ═══════════════ */

export default function IdentityPage() {
  const { data, isLoading } = useIdentityMatches();
  const mergeMatch = useMergeMatch();
  const rejectMatch = useRejectMatch();
  const scanIdentity = useScanIdentity();
  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const [scanDismissed, setScanDismissed] = useState(false);

  const matches = (data?.data ?? []) as IdentityMatch[];
  const pendingMatches = matches
    .filter((m) => m.status === "pending_review")
    .sort((a, b) => (b.match_score ?? 0) - (a.match_score ?? 0));

  const scanResult = scanIdentity.data?.data as Record<string, number> | undefined;

  const showToast = (msg: string) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 3000);
  };

  const handleMerge = (matchId: string) => {
    mergeMatch.mutate(matchId, {
      onSuccess: () => showToast("Contacts merged successfully"),
    });
  };

  const handleReject = (matchId: string) => {
    rejectMatch.mutate(matchId, {
      onSuccess: () => showToast("Marked as not the same"),
    });
  };

  return (
    <div className="min-h-screen bg-stone-50">
      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-6 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-stone-900">Identity Resolution</h1>
            <p className="text-sm text-stone-500 mt-1">Review and merge duplicate contacts</p>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            {pendingMatches.length > 0 && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                {pendingMatches.length} pending review
              </span>
            )}
            <button
              onClick={() => { setScanDismissed(false); scanIdentity.mutate(); }}
              disabled={scanIdentity.isPending}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-teal-600 text-white text-sm font-medium hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
            >
              <ScanSearch className={cn("w-4 h-4", scanIdentity.isPending && "animate-spin")} />
              {scanIdentity.isPending ? "Scanning..." : "Scan for duplicates"}
            </button>
          </div>
        </div>

        {/* Scan progress */}
        {scanIdentity.isPending && (
          <div className="mb-5">
            <div className="bg-teal-50 border border-teal-200 rounded-xl p-4">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-5 h-5 border-2 border-teal-300 border-t-teal-600 rounded-full animate-spin shrink-0" />
                <span className="text-sm font-medium text-teal-800">Scanning contacts for duplicates...</span>
              </div>
              <p className="text-xs text-teal-600 mb-3 ml-8">Comparing names, emails, companies, and social handles...</p>
              <div className="h-1.5 bg-teal-100 rounded-full overflow-hidden">
                <div className="h-full bg-teal-500 rounded-full w-1/4" style={{ animation: "identityIndeterminate 1.5s ease-in-out infinite" }} />
                <style>{`
                  @keyframes identityIndeterminate {
                    0% { transform: translateX(-100%) scaleX(0.4); }
                    50% { transform: translateX(30%) scaleX(0.8); }
                    100% { transform: translateX(110%) scaleX(0.4); }
                  }
                `}</style>
              </div>
            </div>
          </div>
        )}

        {/* Scan error */}
        {scanIdentity.isError && (
          <div className="mb-5 p-3 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">
            Scan failed. Please try again.
          </div>
        )}

        {/* Scan result */}
        {scanIdentity.isSuccess && scanResult && !scanDismissed && (
          <div className="mb-5">
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 flex items-center gap-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
              <p className="text-sm text-emerald-800">
                <strong>Scan complete</strong> — {scanResult.matches_found ?? 0} matches found
                {(scanResult.auto_merged ?? 0) > 0 && `, ${scanResult.auto_merged} auto-merged`}
                {(scanResult.pending_review ?? 0) > 0 && `, ${scanResult.pending_review} pending review`}
              </p>
              <button onClick={() => setScanDismissed(true)} className="ml-auto p-1 rounded text-emerald-500 hover:text-emerald-700 hover:bg-emerald-100 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {/* Match list */}
        {isLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((n) => (
              <div key={n} className="h-48 rounded-xl bg-white border border-stone-200 animate-pulse" />
            ))}
          </div>
        ) : pendingMatches.length === 0 ? (
          /* Empty state */
          <div className="bg-white rounded-xl border border-stone-200 p-12 text-center">
            <div className="w-14 h-14 rounded-full bg-stone-100 flex items-center justify-center mx-auto mb-4">
              <ScanSearch className="w-7 h-7 text-stone-400" />
            </div>
            <h3 className="text-base font-semibold text-stone-700 mb-1">No pending matches</h3>
            <p className="text-sm text-stone-400">Run a scan to detect potential duplicates</p>
            <button
              onClick={() => scanIdentity.mutate()}
              disabled={scanIdentity.isPending}
              className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-teal-600 text-white text-sm font-medium hover:bg-teal-700 disabled:opacity-50 transition-colors shadow-sm"
            >
              <ScanSearch className="w-4 h-4" />
              Scan now
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {pendingMatches.map((match) => (
              <MatchCard
                key={match.id}
                match={match}
                onMerge={() => handleMerge(match.id)}
                onReject={() => handleReject(match.id)}
                merging={mergeMatch.isPending}
                rejecting={rejectMatch.isPending}
              />
            ))}
          </div>
        )}
      </main>

      {/* Toast */}
      {toastMsg && <Toast message={toastMsg} onDismiss={() => setToastMsg(null)} />}
    </div>
  );
}
