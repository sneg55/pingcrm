"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, GitMerge, Minus, X , Search } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { useContactDuplicates, useContacts, useMergeContacts } from "@/hooks/use-contacts";
import { client } from "@/lib/api-client";
import { ContactAvatar } from "@/components/contact-avatar";
import type { components } from "@/lib/api-types";

type ContactResponse = components["schemas"]["ContactResponse"];

// The DuplicateRow can receive either a real detected duplicate (DuplicateContactData)
// or a manually-selected contact (ContactResponse) mapped into the same shape. We accept
// the superset so both paths typecheck without casts.
type DuplicateLike = {
  id: string;
  full_name?: string | null;
  given_name?: string | null;
  family_name?: string | null;
  emails?: string[] | null;
  phones?: string[] | null;
  company?: string | null;
  title?: string | null;
  twitter_handle?: string | null;
  telegram_username?: string | null;
  avatar_url?: string | null;
  source?: string | null;
  score?: number | null;
};

/* ── Duplicate Row ── */

// eslint-disable-next-line sonarjs/cognitive-complexity -- row encapsulates dismiss/merge/confirm states; splitting would just shuffle conditionals across helpers
function DuplicateRow({
  dup,
  contactId,
  onDismissed,
}: {
  dup: DuplicateLike;
  contactId: string;
  onDismissed?: () => void;
}) {
  const mergeContacts = useMergeContacts();
  const queryClient = useQueryClient();
  const router = useRouter();
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [dismissing, setDismissing] = useState(false);

  const name =
    dup.full_name ||
    [dup.given_name, dup.family_name].filter(Boolean).join(" ") ||
    "Unnamed";
  const score = typeof dup.score === "number" ? Math.round(dup.score * 100) : null;

  const [mergeError, setMergeError] = useState<string | null>(null);

  const handleMerge = () => {
    setMergeError(null);
    mergeContacts.mutate(
      { contactId, otherId: dup.id },
      {
        onSuccess: (result) => {
          const survivingId = result?.data?.id;
          if (!survivingId) {
            setMergeError("Merge failed — contact may already be merged or deleted.");
            setConfirmId(null);
            return;
          }
          void queryClient.invalidateQueries({ queryKey: ["contacts"] });
          void queryClient.invalidateQueries({ queryKey: ["contact-duplicates"] });
          if (survivingId !== contactId) {
            router.replace(`/contacts/${survivingId}`);
          } else {
            void queryClient.invalidateQueries({ queryKey: ["contacts", contactId] });
            setConfirmId(null);
          }
        },
        onError: (err) => {
          setMergeError(err?.message || "Merge failed. Please try again.");
          setConfirmId(null);
        },
      }
    );
  };

  const handleDismiss = async () => {
    setDismissing(true);
    try {
      await client.POST(
        "/api/v1/contacts/{contact_id}/dismiss-duplicate/{other_id}",
        { params: { path: { contact_id: contactId, other_id: dup.id } } }
      );
      void queryClient.invalidateQueries({ queryKey: ["contact-duplicates", contactId] });
      onDismissed?.();
    } finally {
      setDismissing(false);
    }
  };

  return (
    <div className="border border-stone-200 dark:border-stone-700 rounded-lg overflow-hidden">
      {score !== null && (
        <div className="flex items-center justify-between px-3 py-2 bg-stone-50 dark:bg-stone-800 border-b border-stone-100 dark:border-stone-700">
          <span
            className={cn(
              "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border",
              score >= 85
                ? "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800"
                : score >= 65
                ? "bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800"
                : "bg-sky-50 dark:bg-sky-950 text-sky-700 dark:text-sky-400 border-sky-200 dark:border-sky-800"
            )}
          >
            {score >= 85
              ? "Strong match"
              : score >= 65
              ? "Probable match"
              : "Possible match"}
          </span>
          <div className="flex items-center gap-1.5">
            <div className="w-12 h-1.5 bg-stone-200 dark:bg-stone-700 rounded-full overflow-hidden">
              <div
                className={cn(
                  "h-full rounded-full",
                  score >= 85 ? "bg-emerald-500" : score >= 65 ? "bg-amber-400" : "bg-sky-400"
                )}
                style={{ width: `${score}%` }}
              />
            </div>
            <span className="font-mono text-xs font-bold text-stone-600 dark:text-stone-300">{score}%</span>
          </div>
        </div>
      )}

      <div className="px-3 py-3">
        <Link
          href={`/contacts/${dup.id}`}
          className="flex items-center gap-2.5 mb-2.5 group/dup"
        >
          <ContactAvatar avatarUrl={dup.avatar_url} name={name} size="xs" />
          <div className="min-w-0">
            <p className="text-xs font-medium text-stone-900 dark:text-stone-100 group-hover/dup:text-teal-700 dark:group-hover/dup:text-teal-400 transition-colors">
              {name}
            </p>
            <p className="text-[10px] text-stone-400 dark:text-stone-500">
              {dup.source ? `Via ${dup.source}` : "Contact"}
            </p>
          </div>
        </Link>

        <div className="space-y-1.5 mb-3">
          {dup.emails?.[0] && (
            <div className="flex items-center gap-2">
              <Check className="w-3 h-3 text-emerald-500 shrink-0" />
              <span className="text-[11px] text-stone-600 dark:text-stone-300">
                Email: <strong className="text-stone-800 dark:text-stone-200">{dup.emails[0]}</strong>
              </span>
            </div>
          )}
          {dup.company && (
            <div className="flex items-center gap-2">
              <Check className="w-3 h-3 text-emerald-500 shrink-0" />
              <span className="text-[11px] text-stone-600 dark:text-stone-300">
                Company: <strong className="text-stone-800 dark:text-stone-200">{dup.company}</strong>
              </span>
            </div>
          )}
          {!dup.twitter_handle && !dup.telegram_username && (
            <div className="flex items-center gap-2">
              <Minus className="w-3 h-3 text-stone-300 dark:text-stone-600 shrink-0" />
              <span className="text-[11px] text-stone-400 dark:text-stone-500">No matching handles</span>
            </div>
          )}
        </div>

        {mergeError && (
          <p className="text-[11px] text-red-500 mb-2">{mergeError}</p>
        )}

        {confirmId === dup.id ? (
          <div className="flex items-center gap-2">
            <button
              onClick={handleMerge}
              disabled={mergeContacts.isPending}
              className="flex-1 inline-flex items-center justify-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-md bg-teal-600 text-white hover:bg-teal-700 disabled:opacity-50 transition-colors"
            >
              {mergeContacts.isPending ? "Merging..." : "Confirm merge"}
            </button>
            <button
              onClick={() => setConfirmId(null)}
              className="flex-1 inline-flex items-center justify-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-md border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors"
            >
              Cancel
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <button
              onClick={() => { void handleDismiss(); }}
              disabled={dismissing}
              className="flex-1 inline-flex items-center justify-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-md border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 disabled:opacity-50 transition-colors"
            >
              <X className="w-3 h-3" /> {dismissing ? "Dismissing..." : "Not the same"}
            </button>
            <button
              onClick={() => setConfirmId(dup.id)}
              className="flex-1 inline-flex items-center justify-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-md bg-teal-600 text-white hover:bg-teal-700 transition-colors"
            >
              <GitMerge className="w-3 h-3" /> Merge
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Duplicates Card ── */

export function DuplicatesCard({ contactId }: { contactId: string }) {
  const { data, isLoading } = useContactDuplicates(contactId, true);
  const duplicates = (data?.data ?? []).filter((d) => d.id !== contactId);
  const [showModal, setShowModal] = useState(false);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  // Debounce search input for API queries
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  // Search all contacts when query is 2+ chars
  const { data: searchData } = useContacts({
    search: debouncedSearch.length >= 2 ? debouncedSearch : undefined,
    page_size: 10,
  });
  const searchResults: ContactResponse[] = debouncedSearch.length >= 2
    ? (searchData?.data ?? []).filter((c) => c.id !== contactId)
    : [];

  if (isLoading || duplicates.length === 0) return null;

  return (
    <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">Possible Duplicates</h3>
        <span className="text-[11px] font-medium text-stone-400 dark:text-stone-500">{duplicates.length} pending</span>
      </div>

      <DuplicateRow dup={duplicates[0]} contactId={contactId} />

      {duplicates.length > 1 && (
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center justify-center gap-1 mt-3 w-full text-[11px] text-teal-600 dark:text-teal-400 hover:text-teal-700 dark:hover:text-teal-300 font-medium"
        >
          View all duplicates ({duplicates.length}) <ArrowRight className="w-3 h-3" />
        </button>
      )}

      {showModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={() => setShowModal(false)}
        >
          <div
            className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 shadow-xl w-full max-w-md max-h-[80vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-stone-100 dark:border-stone-800">
              <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">
                All Duplicates ({duplicates.length})
              </h3>
              <button
                onClick={() => setShowModal(false)}
                className="p-1 rounded-md text-stone-400 dark:text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="px-4 pt-3 pb-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-stone-400 dark:text-stone-500" />
                <input
                  type="text"
                  placeholder="Search all contacts to merge..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full pl-8 pr-3 py-1.5 text-xs border border-stone-200 dark:border-stone-700 rounded-md focus:outline-none focus:ring-2 focus:ring-teal-400 bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
                  autoFocus
                />
              </div>
            </div>
            <div className="overflow-auto px-4 pb-4 space-y-3">
              {debouncedSearch.length >= 2 ? (
                // Show search results from all contacts
                searchResults.length === 0 ? (
                  <p className="text-xs text-stone-400 dark:text-stone-500 text-center py-4">No contacts found</p>
                ) : (
                  searchResults.map((c) => {
                    // Check if this contact is already in duplicates list (has a score)
                    const existingDup: DuplicateLike | undefined = duplicates.find((d) => d.id === c.id);
                    const mergeTarget: DuplicateLike = existingDup || {
                      id: c.id,
                      full_name: c.full_name,
                      given_name: c.given_name,
                      family_name: c.family_name,
                      emails: c.emails,
                      company: c.company,
                      twitter_handle: c.twitter_handle,
                      telegram_username: c.telegram_username,
                      avatar_url: c.avatar_url,
                      source: c.source,
                      score: null, // no duplicate score — manual search
                    };
                    return <DuplicateRow key={c.id} dup={mergeTarget} contactId={contactId} />;
                  })
                )
              ) : (
                // Show detected duplicates when not searching
                duplicates.map((dup) => (
                  <DuplicateRow key={dup.id} dup={dup} contactId={contactId} />
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
