"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Mail,
  Twitter,
  MessageCircle,
  Building2,
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
} from "lucide-react";

import type {
  IdentityMatch,
  IdentityMatchContact,
} from "@/hooks/use-identity";
import { cn } from "@/lib/utils";
import { ContactAvatar } from "@/components/contact-avatar";

type MatchTypeStyle = {
  label: string;
  icon: React.ReactNode;
  pillColors: string;
  barColor: string;
};

function matchTypeStyle(method: string, score: number): MatchTypeStyle {
  if (method === "deterministic" || score >= 0.85) {
    return {
      label: "Exact match",
      icon: <CheckCircle className="w-3.5 h-3.5" />,
      pillColors:
        "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800",
      barColor: "bg-emerald-500",
    };
  }
  if (method === "probabilistic" && score < 0.65) {
    return {
      label: "Probabilistic",
      icon: <HelpCircle className="w-3.5 h-3.5" />,
      pillColors:
        "bg-sky-50 dark:bg-sky-950 text-sky-700 dark:text-sky-400 border-sky-200 dark:border-sky-800",
      barColor: "bg-sky-400",
    };
  }
  return {
    label: "Possible match",
    icon: <AlertCircle className="w-3.5 h-3.5" />,
    pillColors:
      "bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800",
    barColor: "bg-amber-400",
  };
}

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
    <div className="bg-stone-50 dark:bg-stone-800 rounded-lg p-4 border border-stone-100 dark:border-stone-700">
      <div className="flex items-center gap-3 mb-3">
        <ContactAvatar avatarUrl={null} name={displayName} size="sm" />
        <div className="min-w-0 flex-1">
          <Link
            href={`/contacts/${contact.id}`}
            className="text-sm font-semibold text-stone-900 dark:text-stone-100 hover:text-teal-700 dark:hover:text-teal-400 transition-colors truncate block"
            onClick={(e) => e.stopPropagation()}
          >
            {displayName}
          </Link>
          {contact.source && (
            <p className="text-xs text-stone-400 dark:text-stone-500">
              Added via {contact.source}
            </p>
          )}
        </div>
      </div>

      <div className="space-y-1.5 text-xs text-stone-600 dark:text-stone-300">
        {contact.company && (
          <div className="flex items-center gap-2">
            <Building2 className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
            <span>{contact.company}</span>
          </div>
        )}
        {primaryEmail && (
          <div className="flex items-center gap-2">
            <Mail className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
            <span className="font-mono truncate">{primaryEmail}</span>
          </div>
        )}
        {contact.twitter_handle ? (
          <div className="flex items-center gap-2">
            <Twitter className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
            <span className="font-mono">@{contact.twitter_handle}</span>
          </div>
        ) : null}
        {contact.telegram_username ? (
          <div className="flex items-center gap-2">
            <MessageCircle className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
            <span className="font-mono">@{contact.telegram_username}</span>
          </div>
        ) : null}
      </div>

      {hasExtra && (
        <>
          <button
            onClick={() => setExpanded(!expanded)}
            className="mt-3 text-xs text-teal-600 dark:text-teal-400 hover:text-teal-800 dark:hover:text-teal-300 transition-colors flex items-center gap-1"
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {expanded ? "Less" : "More details"}
          </button>

          {expanded && (
            <div className="mt-2 pt-2 border-t border-stone-200 dark:border-stone-700 space-y-1.5 text-xs text-stone-600 dark:text-stone-300">
              {contact.title && (
                <div className="flex items-center gap-2">
                  <Briefcase className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
                  <span className="truncate">{contact.title}</span>
                </div>
              )}
              {extraEmails.map((email) => (
                <div key={email} className="flex items-center gap-2 truncate">
                  <Mail className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
                  <span className="font-mono truncate">{email}</span>
                </div>
              ))}
              {contact.phones.map((phone) => (
                <div key={phone} className="flex items-center gap-2">
                  <Phone className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
                  <span className="font-mono">{phone}</span>
                </div>
              ))}
              {contact.linkedin_url && (
                <div className="flex items-center gap-2 truncate">
                  <Globe className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
                  <a href={contact.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-teal-600 dark:text-teal-400 hover:underline font-mono truncate">
                    LinkedIn
                  </a>
                </div>
              )}
              {contact.tags.length > 0 && (
                <div className="flex items-start gap-2">
                  <Tag className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0 mt-0.5" />
                  <div className="flex flex-wrap gap-1">
                    {contact.tags.map((tag) => (
                      <span key={tag} className="px-1.5 py-0.5 rounded text-xs bg-stone-200 dark:bg-stone-700 text-stone-700 dark:text-stone-300">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {contact.notes && (
                <div className="flex items-start gap-2">
                  <FileText className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0 mt-0.5" />
                  <span className="text-xs text-stone-500 dark:text-stone-400 line-clamp-3">{contact.notes}</span>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function MatchCard({
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
    <div className="card-hover bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 overflow-hidden">
      <div className="p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3 flex-wrap">
            <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border", style.pillColors)}>
              {style.icon}
              {style.label}
            </span>
            <div className="flex items-center gap-2">
              <span className="text-sm font-mono font-medium text-stone-700 dark:text-stone-300">{pct}% match</span>
              <div className="w-24 h-1.5 bg-stone-100 dark:bg-stone-800 rounded-full overflow-hidden">
                <div className={cn("h-full rounded-full", style.barColor)} style={{ width: `${pct}%` }} />
              </div>
            </div>
            {isAutoMergeReady && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-teal-50 dark:bg-teal-950 text-teal-700 dark:text-teal-400 border border-teal-200 dark:border-teal-800">
                <Zap className="w-3 h-3" />
                Auto-merge ready
              </span>
            )}
          </div>
          <button
            onClick={() => setBreakdownOpen((v) => !v)}
            className="text-xs text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 transition-colors flex items-center gap-1"
          >
            <BarChart2 className="w-3.5 h-3.5" />
            Match detail
          </button>
        </div>

        {breakdownOpen && (
          <div className="mb-4">
            <div className="bg-stone-50 dark:bg-stone-800 rounded-lg p-4 border border-stone-100 dark:border-stone-700">
              <p className="text-xs font-medium text-stone-500 dark:text-stone-400 mb-3 uppercase tracking-wide">Match breakdown</p>
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
                      <span className="text-xs text-stone-600 dark:text-stone-300 w-32 shrink-0">{item.label}</span>
                      <div className="flex-1 h-1.5 bg-stone-200 dark:bg-stone-700 rounded-full overflow-hidden">
                        <div
                          className={cn("h-full rounded-full", hasMatch ? style.barColor : "bg-stone-300 dark:bg-stone-600")}
                          style={{ width: `${contribution}%` }}
                        />
                      </div>
                      <span className="text-xs font-mono text-stone-400 dark:text-stone-500 w-8 text-right">{contribution}%</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        <div className="grid grid-cols-[1fr_auto_1fr] gap-4 items-stretch">
          <ContactPanel contact={match.contact_a as IdentityMatchContact} />
          <div className="flex items-center justify-center">
            <div className="flex flex-col items-center gap-1">
              <div className="w-px h-8 bg-stone-200 dark:bg-stone-700" />
              <span className="text-xs font-mono font-medium text-stone-400 dark:text-stone-500 bg-stone-100 dark:bg-stone-800 rounded px-1.5 py-0.5">vs</span>
              <div className="w-px h-8 bg-stone-200 dark:bg-stone-700" />
            </div>
          </div>
          <ContactPanel contact={match.contact_b as IdentityMatchContact} />
        </div>
      </div>

      <div className="px-5 py-3 border-t border-stone-100 dark:border-stone-800 bg-stone-50 dark:bg-stone-800 flex items-center justify-between">
        {isLowConfidence && (
          <p className="text-xs text-stone-400 dark:text-stone-500">Low confidence — manual review recommended</p>
        )}
        <div className={cn("flex items-center gap-2", !isLowConfidence && "ml-auto")}>
          <button
            onClick={onReject}
            disabled={rejecting}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-stone-600 dark:text-stone-300 border border-stone-200 dark:border-stone-700 hover:bg-stone-100 dark:hover:bg-stone-800 disabled:opacity-50 transition-colors"
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
