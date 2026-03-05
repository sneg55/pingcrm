"use client";

import { Mail, Twitter, MessageCircle, Building2, ScanSearch, GitMerge, X } from "lucide-react";
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
  const displayName = contact.full_name ?? "Unnamed";
  const primaryEmail = contact.emails[0] ?? null;

  return (
    <div className="flex-1 min-w-0 p-4 bg-gray-50 rounded-lg border border-gray-200">
      {/* Avatar + name */}
      <div className="flex items-center gap-3 mb-3">
        <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-semibold text-sm flex-shrink-0">
          {getInitials(displayName)}
        </div>
        <div className="min-w-0">
          <p className="font-semibold text-gray-900 truncate">{displayName}</p>
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
    </div>
  );
}

export default function IdentityPage() {
  const { data, isLoading } = useIdentityMatches();
  const mergeMatch = useMergeMatch();
  const rejectMatch = useRejectMatch();
  const scanIdentity = useScanIdentity();

  const matches = data?.data ?? [];
  const pendingMatches = matches.filter((m) => m.status === "pending");

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
            <ScanSearch className="w-4 h-4" />
            {scanIdentity.isPending ? "Scanning..." : "Scan for duplicates"}
          </button>
        </div>

        {/* Scan result feedback */}
        {scanIdentity.isSuccess && scanIdentity.data && (
          <div className="mb-4 p-3 rounded-lg bg-green-50 border border-green-200 text-sm text-green-700">
            Scan complete — {scanIdentity.data.data?.matches_found ?? 0} potential{" "}
            {(scanIdentity.data.data?.matches_found ?? 0) === 1 ? "match" : "matches"} found.
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
