"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Mail, Twitter, MessageCircle, Building2, ScanSearch, GitMerge, X,
  Phone, Briefcase, Tag, FileText, Globe, ChevronDown, ChevronUp,
} from "lucide-react";
import {
  useIdentityMatches,
  useMergeMatch,
  useRejectMatch,
  useScanIdentity,
  type IdentityMatchContact,
} from "@/hooks/use-identity";

function getInitials(name: string | null): string {
  if (!name) return "?";
  return name
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
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
    <div className="flex-1 min-w-0 p-4 bg-gray-50 rounded-lg border border-gray-200">
      {/* Avatar + name */}
      <div className="flex items-center gap-3 mb-3">
        <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-semibold text-sm flex-shrink-0">
          {getInitials(displayName)}
        </div>
        <div className="min-w-0 flex-1">
          <Link
            href={`/contacts/${contact.id}`}
            className="font-semibold text-blue-600 hover:text-blue-800 hover:underline truncate block"
            onClick={(e) => e.stopPropagation()}
          >
            {displayName}
          </Link>
          {contact.company && (
            <p className="text-xs text-gray-500 truncate flex items-center gap-1">
              <Building2 className="w-3 h-3 flex-shrink-0" />
              {contact.company}
            </p>
          )}
        </div>
      </div>

      <ul className="space-y-1.5 text-sm">
        {primaryEmail && (
          <li className="flex items-center gap-2 text-gray-600 truncate">
            <Mail className="w-3.5 h-3.5 flex-shrink-0 text-gray-400" />
            <span className="truncate">{primaryEmail}</span>
          </li>
        )}
        {contact.twitter_handle && (
          <li className="flex items-center gap-2 text-gray-600">
            <Twitter className="w-3.5 h-3.5 flex-shrink-0 text-gray-400" />
            <span>@{contact.twitter_handle}</span>
          </li>
        )}
        {contact.telegram_username && (
          <li className="flex items-center gap-2 text-gray-600">
            <MessageCircle className="w-3.5 h-3.5 flex-shrink-0 text-gray-400" />
            <span>@{contact.telegram_username}</span>
          </li>
        )}
      </ul>

      {/* Expand toggle */}
      {hasExtra && (
        <>
          <button
            onClick={() => setExpanded(!expanded)}
            className="mt-2 text-xs text-blue-600 hover:text-blue-800 flex items-center gap-0.5"
          >
            {expanded ? (
              <>
                <ChevronUp className="w-3 h-3" />
                Less
              </>
            ) : (
              <>
                <ChevronDown className="w-3 h-3" />
                More details
              </>
            )}
          </button>

          {expanded && (
            <ul className="mt-2 pt-2 border-t border-gray-200 space-y-1.5 text-sm">
              {contact.title && (
                <li className="flex items-center gap-2 text-gray-600">
                  <Briefcase className="w-3.5 h-3.5 flex-shrink-0 text-gray-400" />
                  <span className="truncate">{contact.title}</span>
                </li>
              )}
              {extraEmails.map((email) => (
                <li key={email} className="flex items-center gap-2 text-gray-600 truncate">
                  <Mail className="w-3.5 h-3.5 flex-shrink-0 text-gray-400" />
                  <span className="truncate">{email}</span>
                </li>
              ))}
              {contact.phones.map((phone) => (
                <li key={phone} className="flex items-center gap-2 text-gray-600">
                  <Phone className="w-3.5 h-3.5 flex-shrink-0 text-gray-400" />
                  <span>{phone}</span>
                </li>
              ))}
              {contact.linkedin_url && (
                <li className="flex items-center gap-2 text-gray-600 truncate">
                  <Globe className="w-3.5 h-3.5 flex-shrink-0 text-gray-400" />
                  <a
                    href={contact.linkedin_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline truncate"
                  >
                    LinkedIn
                  </a>
                </li>
              )}
              {contact.tags.length > 0 && (
                <li className="flex items-start gap-2 text-gray-600">
                  <Tag className="w-3.5 h-3.5 flex-shrink-0 text-gray-400 mt-0.5" />
                  <div className="flex flex-wrap gap-1">
                    {contact.tags.map((tag) => (
                      <span
                        key={tag}
                        className="px-1.5 py-0.5 rounded text-xs bg-gray-200 text-gray-700"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </li>
              )}
              {contact.notes && (
                <li className="flex items-start gap-2 text-gray-600">
                  <FileText className="w-3.5 h-3.5 flex-shrink-0 text-gray-400 mt-0.5" />
                  <span className="text-xs text-gray-500 line-clamp-3">{contact.notes}</span>
                </li>
              )}
              {contact.source && (
                <li className="text-xs text-gray-400 mt-1">
                  Source: {contact.source}
                </li>
              )}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

export default function IdentityPage() {
  const { data, isLoading } = useIdentityMatches();
  const mergeMatch = useMergeMatch();
  const rejectMatch = useRejectMatch();
  const scanIdentity = useScanIdentity();

  const matches = data?.data ?? [];
  const pendingMatches = matches
    .filter((m) => m.status === "pending_review")
    .sort((a, b) => b.match_score - a.match_score);

  const scanResult = scanIdentity.data?.data;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Identity Resolution</h1>
            <p className="text-sm text-gray-500 mt-1">
              Review and merge duplicate contacts
            </p>
          </div>
          <button
            onClick={() => scanIdentity.mutate()}
            disabled={scanIdentity.isPending}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <ScanSearch className={`w-4 h-4 ${scanIdentity.isPending ? "animate-spin" : ""}`} />
            {scanIdentity.isPending ? "Scanning..." : "Scan for duplicates"}
          </button>
        </div>

        {/* Scanning progress */}
        {scanIdentity.isPending && (
          <div className="mb-6 p-4 rounded-lg bg-blue-50 border border-blue-200">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-5 h-5 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm font-medium text-blue-800">Scanning contacts for duplicates...</p>
            </div>
            <p className="text-xs text-blue-600 ml-8">
              Comparing names, emails, companies, and social handles across all contacts. This may take a moment.
            </p>
            <div className="mt-3 ml-8 h-1.5 rounded-full bg-blue-100 overflow-hidden">
              <div className="h-full rounded-full bg-blue-500 animate-pulse" style={{ width: "60%" }} />
            </div>
          </div>
        )}

        {/* Scan error */}
        {scanIdentity.isError && (
          <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
            Scan failed. Please try again.
          </div>
        )}

        {/* Scan result feedback */}
        {scanIdentity.isSuccess && scanResult && (
          <div className="mb-4 p-4 rounded-lg bg-green-50 border border-green-200">
            <p className="text-sm font-medium text-green-800">
              Scan complete
            </p>
            <div className="mt-2 flex gap-4 text-sm text-green-700">
              <span>{scanResult.matches_found ?? 0} matches found</span>
              {(scanResult.auto_merged ?? 0) > 0 && (
                <span className="flex items-center gap-1">
                  <GitMerge className="w-3.5 h-3.5" />
                  {scanResult.auto_merged} auto-merged
                </span>
              )}
              {(scanResult.pending_review ?? 0) > 0 && (
                <span>{scanResult.pending_review} pending review</span>
              )}
            </div>
          </div>
        )}

        {/* Match list */}
        {isLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((n) => (
              <div
                key={n}
                className="h-40 rounded-xl bg-white border border-gray-200 animate-pulse"
              />
            ))}
          </div>
        ) : pendingMatches.length === 0 ? (
          <div className="text-center py-20 text-gray-400">
            <ScanSearch className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p className="text-sm">No pending matches</p>
            <p className="text-xs mt-1">
              Run a scan to detect potential duplicates.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {pendingMatches.map((match) => (
              <div
                key={match.id}
                className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm"
              >
                {/* Match meta */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-100">
                      {match.match_method}
                    </span>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-bold text-gray-900">
                      {Math.round(match.match_score * 100)}% match
                    </p>
                    <div className="w-24 h-1.5 rounded-full bg-gray-100 mt-1 ml-auto">
                      <div
                        className="h-1.5 rounded-full bg-blue-500"
                        style={{ width: `${Math.round(match.match_score * 100)}%` }}
                      />
                    </div>
                  </div>
                </div>

                {/* Side-by-side comparison */}
                <div className="flex gap-3 mb-4">
                  <ContactPanel contact={match.contact_a} />
                  <div className="flex items-center text-gray-300 flex-shrink-0">
                    <span className="text-lg font-light">vs</span>
                  </div>
                  <ContactPanel contact={match.contact_b} />
                </div>

                {/* Actions */}
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => rejectMatch.mutate(match.id)}
                    disabled={rejectMatch.isPending}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md text-gray-600 border border-gray-200 hover:bg-gray-50 disabled:opacity-50 transition-colors"
                  >
                    <X className="w-4 h-4" />
                    Not the same
                  </button>
                  <button
                    onClick={() => mergeMatch.mutate(match.id)}
                    disabled={mergeMatch.isPending}
                    className="inline-flex items-center gap-1.5 px-4 py-1.5 text-sm font-medium rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
                  >
                    <GitMerge className="w-4 h-4" />
                    Merge
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
