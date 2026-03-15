"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, GitMerge, Minus, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { useContactDuplicates, useMergeContacts } from "@/hooks/use-contacts";
import { client } from "@/lib/api-client";
import { avatarColor, getInitials } from "../_lib/formatters";

/* ── Duplicate Row ── */

function DuplicateRow({
  dup,
  contactId,
  onDismissed,
}: {
  dup: any;
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

  const handleMerge = () => {
    mergeContacts.mutate(
      { contactId, otherId: dup.id },
      {
        onSuccess: (result: any) => {
          void queryClient.invalidateQueries({ queryKey: ["contacts"] });
          void queryClient.invalidateQueries({ queryKey: ["contact-duplicates"] });
          const survivingId = result?.data?.id;
          if (survivingId && survivingId !== contactId) {
            router.replace(`/contacts/${survivingId}`);
          }
        },
      }
    );
  };

  const handleDismiss = async () => {
    setDismissing(true);
    try {
      await client.POST(
        `/api/v1/contacts/${contactId}/dismiss-duplicate/${dup.id}` as any,
        {}
      );
      void queryClient.invalidateQueries({ queryKey: ["contact-duplicates", contactId] });
      onDismissed?.();
    } finally {
      setDismissing(false);
    }
  };

  return (
    <div className="border border-stone-200 rounded-lg overflow-hidden">
      {score !== null && (
        <div className="flex items-center justify-between px-3 py-2 bg-stone-50 border-b border-stone-100">
          <span
            className={cn(
              "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border",
              score >= 85
                ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                : score >= 65
                ? "bg-amber-50 text-amber-700 border-amber-200"
                : "bg-sky-50 text-sky-700 border-sky-200"
            )}
          >
            {score >= 85
              ? "Strong match"
              : score >= 65
              ? "Probable match"
              : "Possible match"}
          </span>
          <div className="flex items-center gap-1.5">
            <div className="w-12 h-1.5 bg-stone-200 rounded-full overflow-hidden">
              <div
                className={cn(
                  "h-full rounded-full",
                  score >= 85 ? "bg-emerald-500" : score >= 65 ? "bg-amber-400" : "bg-sky-400"
                )}
                style={{ width: `${score}%` }}
              />
            </div>
            <span className="font-mono text-xs font-bold text-stone-600">{score}%</span>
          </div>
        </div>
      )}

      <div className="px-3 py-3">
        <Link
          href={`/contacts/${dup.id}`}
          className="flex items-center gap-2.5 mb-2.5 group/dup"
        >
          <div
            className={cn(
              "w-8 h-8 rounded-full flex items-center justify-center text-[11px] font-semibold shrink-0",
              avatarColor(name)
            )}
          >
            {getInitials(name)}
          </div>
          <div className="min-w-0">
            <p className="text-xs font-medium text-stone-900 group-hover/dup:text-teal-700 transition-colors">
              {name}
            </p>
            <p className="text-[10px] text-stone-400">
              {dup.source ? `Via ${dup.source}` : "Contact"}
            </p>
          </div>
        </Link>

        <div className="space-y-1.5 mb-3">
          {dup.emails?.[0] && (
            <div className="flex items-center gap-2">
              <Check className="w-3 h-3 text-emerald-500 shrink-0" />
              <span className="text-[11px] text-stone-600">
                Email: <strong className="text-stone-800">{dup.emails[0]}</strong>
              </span>
            </div>
          )}
          {dup.company && (
            <div className="flex items-center gap-2">
              <Check className="w-3 h-3 text-emerald-500 shrink-0" />
              <span className="text-[11px] text-stone-600">
                Company: <strong className="text-stone-800">{dup.company}</strong>
              </span>
            </div>
          )}
          {!dup.twitter_handle && !dup.telegram_username && (
            <div className="flex items-center gap-2">
              <Minus className="w-3 h-3 text-stone-300 shrink-0" />
              <span className="text-[11px] text-stone-400">No matching handles</span>
            </div>
          )}
        </div>

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
              className="flex-1 inline-flex items-center justify-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-md border border-stone-200 text-stone-600 hover:bg-stone-50 transition-colors"
            >
              Cancel
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <button
              onClick={handleDismiss}
              disabled={dismissing}
              className="flex-1 inline-flex items-center justify-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-md border border-stone-200 text-stone-600 hover:bg-stone-50 disabled:opacity-50 transition-colors"
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
  const duplicates = (data?.data ?? []).filter((d: any) => d.id !== contactId);
  const [showModal, setShowModal] = useState(false);

  if (isLoading || duplicates.length === 0) return null;

  return (
    <div className="bg-white rounded-xl border border-stone-200 p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-stone-900">Possible Duplicates</h3>
        <span className="text-[11px] font-medium text-stone-400">{duplicates.length} pending</span>
      </div>

      <DuplicateRow dup={duplicates[0]} contactId={contactId} />

      {duplicates.length > 1 && (
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center justify-center gap-1 mt-3 w-full text-[11px] text-teal-600 hover:text-teal-700 font-medium"
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
            className="bg-white rounded-xl border border-stone-200 shadow-xl w-full max-w-md max-h-[80vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-stone-100">
              <h3 className="text-sm font-semibold text-stone-900">
                All Duplicates ({duplicates.length})
              </h3>
              <button
                onClick={() => setShowModal(false)}
                className="p-1 rounded-md text-stone-400 hover:bg-stone-100 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="overflow-auto p-4 space-y-3">
              {duplicates.map((dup: any) => (
                <DuplicateRow key={dup.id} dup={dup} contactId={contactId} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
