"use client";

import { useState } from "react";
import {
  X,
  ScanSearch,
  CheckCircle2,
} from "lucide-react";
import {
  useIdentityMatches,
  useMergeMatch,
  useRejectMatch,
  useScanIdentity,
  type IdentityMatch,
} from "@/hooks/use-identity";
import { cn } from "@/lib/utils";

import { MatchCard } from "./_components/match-card";

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
      onError: (err) => showToast(`Merge failed: ${err.message}`),
    });
  };

  const handleReject = (matchId: string) => {
    rejectMatch.mutate(matchId, {
      onSuccess: () => showToast("Marked as not the same"),
      onError: (err) => showToast(`Reject failed: ${err.message}`),
    });
  };

  return (
    <div className="min-h-screen bg-stone-50 dark:bg-stone-950">
      <main className="max-w-6xl mx-auto px-4 py-8">
        <div className="animate-in stagger-1 mb-6 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-stone-900 dark:text-stone-100">Identity Resolution</h1>
            <p className="text-sm text-stone-500 dark:text-stone-400 mt-1">Review and merge duplicate contacts</p>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            {pendingMatches.length > 0 && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800">
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

        {scanIdentity.isPending && (
          <div className="mb-5">
            <div className="bg-teal-50 dark:bg-teal-950 border border-teal-200 dark:border-teal-800 rounded-xl p-4">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-5 h-5 border-2 border-teal-300 border-t-teal-600 rounded-full animate-spin shrink-0" />
                <span className="text-sm font-medium text-teal-800 dark:text-teal-300">Scanning contacts for duplicates...</span>
              </div>
              <p className="text-xs text-teal-600 dark:text-teal-400 mb-3 ml-8">Comparing names, emails, companies, and social handles...</p>
              <div className="h-1.5 bg-teal-100 dark:bg-teal-900 rounded-full overflow-hidden">
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

        {scanIdentity.isError && (
          <div className="mb-5 p-3 rounded-xl bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-sm text-red-700 dark:text-red-400">
            Scan failed. Please try again.
          </div>
        )}

        {scanIdentity.isSuccess && scanResult && !scanDismissed && (
          <div className="mb-5">
            <div className="bg-emerald-50 dark:bg-emerald-950 border border-emerald-200 dark:border-emerald-800 rounded-xl p-4 flex items-center gap-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400 shrink-0" />
              <p className="text-sm text-emerald-800 dark:text-emerald-300">
                <strong>Scan complete</strong> — {scanResult.matches_found ?? 0} matches found
                {(scanResult.auto_merged ?? 0) > 0 && `, ${scanResult.auto_merged} auto-merged`}
                {(scanResult.pending_review ?? 0) > 0 && `, ${scanResult.pending_review} pending review`}
              </p>
              <button onClick={() => setScanDismissed(true)} className="ml-auto p-1 rounded text-emerald-500 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-emerald-900 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {isLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((n) => (
              <div key={n} className="h-48 rounded-xl bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 animate-pulse" />
            ))}
          </div>
        ) : pendingMatches.length === 0 ? (
          <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-12 text-center">
            <div className="w-14 h-14 rounded-full bg-stone-100 dark:bg-stone-800 flex items-center justify-center mx-auto mb-4">
              <ScanSearch className="w-7 h-7 text-stone-400 dark:text-stone-500" />
            </div>
            <h3 className="text-base font-semibold text-stone-700 dark:text-stone-300 mb-1">No pending matches</h3>
            <p className="text-sm text-stone-400 dark:text-stone-500">Run a scan to detect potential duplicates</p>
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
          <div className="animate-in stagger-2 space-y-4">
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

      {toastMsg && <Toast message={toastMsg} onDismiss={() => setToastMsg(null)} />}
    </div>
  );
}
