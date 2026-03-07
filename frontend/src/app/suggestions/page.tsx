"use client";

import { useState, type ReactNode } from "react";
import {
  Mail,
  MessageCircle,
  Twitter,
  Sparkles,
  Clock,
  X,
  ChevronDown,
} from "lucide-react";
import {
  useSuggestions,
  useUpdateSuggestion,
  useGenerateSuggestions,
  type Suggestion,
} from "@/hooks/use-suggestions";
import { MessageEditor } from "@/components/message-editor";
import Link from "next/link";
import { cn } from "@/lib/utils";

type Channel = "email" | "telegram" | "twitter";

const channelIcons: Record<Channel, ReactNode> = {
  email: <Mail className="w-3.5 h-3.5" />,
  telegram: <MessageCircle className="w-3.5 h-3.5" />,
  twitter: <Twitter className="w-3.5 h-3.5" />,
};

const channelColors: Record<Channel, string> = {
  email: "text-blue-600 bg-blue-50 border-blue-100",
  telegram: "text-sky-600 bg-sky-50 border-sky-100",
  twitter: "text-slate-600 bg-slate-50 border-slate-100",
};

const snoozeOptions = [
  { label: "2 weeks", days: 14 },
  { label: "1 month", days: 30 },
  { label: "3 months", days: 90 },
];

function getInitials(name: string | null): string {
  if (!name) return "?";
  return name
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function SuggestionCard({ suggestion }: { suggestion: Suggestion }) {
  const updateSuggestion = useUpdateSuggestion();
  const [snoozeOpen, setSnoozeOpen] = useState(false);
  const [showEditor, setShowEditor] = useState(false);

  const c = suggestion.contact;
  const displayName =
    c?.full_name ??
    ([c?.given_name, c?.family_name].filter(Boolean).join(" ") || "Unknown contact");
  const channel = suggestion.suggested_channel;

  const triggerLabels: Record<string, string> = {
    time_based: "No interaction in 90+ days",
    event_based: "New event detected",
    scheduled: "Scheduled follow-up",
  };
  const triggerReason = triggerLabels[suggestion.trigger_type] ?? suggestion.trigger_type;

  const handleSend = (message: string, ch: Channel) => {
    updateSuggestion.mutate({
      id: suggestion.id,
      input: { status: "sent", suggested_message: message, suggested_channel: ch },
    });
  };

  const handleSnooze = (days: number) => {
    const snoozeUntil = new Date(
      Date.now() + days * 24 * 60 * 60 * 1000
    ).toISOString();
    updateSuggestion.mutate({
      id: suggestion.id,
      input: { status: "snoozed", snooze_until: snoozeUntil },
    });
    setSnoozeOpen(false);
  };

  const handleDismiss = () => {
    updateSuggestion.mutate({
      id: suggestion.id,
      input: { status: "dismissed" },
    });
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm space-y-4">
      {/* Contact header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-semibold text-sm flex-shrink-0">
            {getInitials(displayName)}
          </div>
          <div className="min-w-0">
            <Link
              href={`/contacts/${suggestion.contact_id}`}
              className="font-semibold text-blue-600 hover:text-blue-800 hover:underline truncate block"
            >
              {displayName}
            </Link>
            <p className="text-xs text-gray-500 truncate mt-0.5">
              {triggerReason}
            </p>
          </div>
        </div>
        <span
          className={cn(
            "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border flex-shrink-0",
            channelColors[channel]
          )}
        >
          {channelIcons[channel]}
          {channel}
        </span>
      </div>

      {/* Draft preview or editor */}
      {showEditor ? (
        <MessageEditor
          suggestionId={suggestion.id}
          initialMessage={suggestion.suggested_message}
          initialChannel={channel}
          onSend={handleSend}
        />
      ) : (
        <div
          className="text-sm text-gray-700 bg-gray-50 rounded-md p-3 border border-gray-100 cursor-pointer hover:border-blue-200 transition-colors"
          onClick={() => setShowEditor(true)}
          title="Click to edit"
        >
          {suggestion.suggested_message}
        </div>
      )}

      {/* Action buttons */}
      {!showEditor && (
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowEditor(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 transition-colors"
            disabled={updateSuggestion.isPending}
          >
            Send
          </button>

          {/* Snooze with dropdown */}
          <div className="relative">
            <div className="inline-flex rounded-md border border-yellow-300 overflow-hidden">
              <button
                onClick={() => handleSnooze(14)}
                className="px-3 py-1.5 text-sm text-yellow-700 bg-yellow-50 hover:bg-yellow-100 transition-colors"
                disabled={updateSuggestion.isPending}
              >
                Snooze
              </button>
              <button
                onClick={() => setSnoozeOpen((v) => !v)}
                className="px-2 py-1.5 text-yellow-700 bg-yellow-50 hover:bg-yellow-100 border-l border-yellow-300 transition-colors"
                aria-label="Snooze options"
              >
                <ChevronDown className="w-3.5 h-3.5" />
              </button>
            </div>
            {snoozeOpen && (
              <div className="absolute left-0 top-full mt-1 w-36 bg-white rounded-lg border border-gray-200 shadow-md py-1 z-10">
                {snoozeOptions.map((opt) => (
                  <button
                    key={opt.days}
                    onClick={() => handleSnooze(opt.days)}
                    className="w-full text-left px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2"
                  >
                    <Clock className="w-3.5 h-3.5 text-gray-400" />
                    {opt.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={handleDismiss}
            disabled={updateSuggestion.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md text-gray-500 border border-gray-200 hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            <X className="w-3.5 h-3.5" />
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}

export default function SuggestionsPage() {
  const { data, isLoading } = useSuggestions();
  const generateSuggestions = useGenerateSuggestions();

  const allSuggestions = data?.data ?? [];
  const pendingSuggestions = allSuggestions.filter(
    (s) => s.status === "pending"
  );

  const genResult = generateSuggestions.data?.data;
  const genMeta = generateSuggestions.data?.meta;
  const genCount = (genMeta as Record<string, number> | undefined)?.generated ?? genResult?.length ?? 0;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-3xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              Weekly Digest
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              AI-suggested follow-ups for your network
            </p>
          </div>
          <button
            onClick={() => generateSuggestions.mutate()}
            disabled={generateSuggestions.isPending}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Sparkles className={`w-4 h-4 ${generateSuggestions.isPending ? "animate-spin" : ""}`} />
            {generateSuggestions.isPending
              ? "Generating..."
              : "Generate new suggestions"}
          </button>
        </div>

        {/* Generation progress */}
        {generateSuggestions.isPending && (
          <div className="mb-6 p-4 rounded-lg bg-indigo-50 border border-indigo-200">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-5 h-5 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm font-medium text-indigo-800">Generating follow-up suggestions...</p>
            </div>
            <p className="text-xs text-indigo-600 ml-8">
              Analyzing your contacts, interaction history, and relationship scores. This may take a moment.
            </p>
            <div className="mt-3 ml-8 h-1.5 rounded-full bg-indigo-100 overflow-hidden">
              <div className="h-full rounded-full bg-indigo-500 animate-pulse" style={{ width: "60%" }} />
            </div>
          </div>
        )}

        {/* Generation error */}
        {generateSuggestions.isError && (
          <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
            Failed to generate suggestions. Please try again.
          </div>
        )}

        {/* Generation success */}
        {generateSuggestions.isSuccess && (
          <div className="mb-4 p-4 rounded-lg bg-green-50 border border-green-200">
            <p className="text-sm font-medium text-green-800">
              Generation complete
            </p>
            <p className="text-sm text-green-700 mt-1">
              {genCount > 0
                ? `${genCount} new suggestion${genCount !== 1 ? "s" : ""} generated.`
                : "No new suggestions — your network is in good shape!"}
            </p>
          </div>
        )}

        {/* Content */}
        {isLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((n) => (
              <div
                key={n}
                className="h-44 rounded-xl bg-white border border-gray-200 animate-pulse"
              />
            ))}
          </div>
        ) : pendingSuggestions.length === 0 ? (
          <div className="text-center py-20 text-gray-400">
            <Sparkles className="w-10 h-10 mx-auto mb-3 opacity-30" />
            <p className="text-sm">No pending suggestions</p>
            <p className="text-xs mt-1">
              Generate new suggestions to get started.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {pendingSuggestions.map((suggestion) => (
              <SuggestionCard key={suggestion.id} suggestion={suggestion} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
