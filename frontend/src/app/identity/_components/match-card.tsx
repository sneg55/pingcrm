"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Mail,
  Twitter,
  MessageCircle,
  Building2,
  Phone,
  Briefcase,
  Tag,
  FileText,
  Globe,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

import type {
  IdentityMatch,
  IdentityMatchContact,
} from "@/hooks/use-identity";
import { ContactAvatar } from "@/components/contact-avatar";
import { MatchCardShell, type BreakdownRow } from "./match-card-shell";

const CONTACT_BREAKDOWN: BreakdownRow[] = [
  { label: "Email domain", weight: 40 },
  { label: "Name similarity", weight: 20 },
  { label: "Same company", weight: 20 },
  { label: "Username", weight: 10 },
  { label: "Mutual signals", weight: 10 },
];

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
  return (
    <MatchCardShell
      matchScore={match.match_score ?? 0}
      matchMethod={match.match_method}
      breakdownRows={CONTACT_BREAKDOWN}
      leftPanel={<ContactPanel contact={match.contact_a as IdentityMatchContact} />}
      rightPanel={<ContactPanel contact={match.contact_b as IdentityMatchContact} />}
      mergeButtonLabel="Merge"
      onMerge={onMerge}
      onReject={onReject}
      merging={merging}
      rejecting={rejecting}
    />
  );
}
