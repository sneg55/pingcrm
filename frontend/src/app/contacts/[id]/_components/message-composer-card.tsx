"use client";

import { useState, useRef, useEffect } from "react";
import { ChevronDown, Clock, Send, Sparkles, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { MessageEditor } from "@/components/message-editor";
import {
  useContactSuggestion,
  useUpdateSuggestion,
  useSendMessage,
} from "@/hooks/use-suggestions";
import { type Contact } from "@/hooks/use-contacts";
import { client } from "@/lib/api-client";

export function MessageComposerCard({
  contact,
  contactId,
}: {
  contact: Contact;
  contactId: string;
}) {
  const suggestion = useContactSuggestion(contactId);
  const updateSuggestion = useUpdateSuggestion();
  const sendMessage = useSendMessage();
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showSnooze, setShowSnooze] = useState(false);
  const snoozeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showSnooze) return;
    const handler = (e: MouseEvent) => {
      if (snoozeRef.current && !snoozeRef.current.contains(e.target as Node)) {
        setShowSnooze(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showSnooze]);

  const hasSuggestion = Boolean(suggestion);

  const disabledChannels = {
    ...(!contact.emails?.length ? { email: "No email" as const } : {}),
    ...(!contact.telegram_username ? { telegram: "No Telegram" as const } : {}),
    ...(!contact.twitter_handle ? { twitter: "No Twitter" as const } : {}),
  };

  const handleSnooze = (days: number) => {
    if (!suggestion) return;
    const date = new Date();
    date.setDate(date.getDate() + days);
    updateSuggestion.mutate({
      id: suggestion.id,
      input: { status: "snoozed", snooze_until: date.toISOString() },
    });
    setShowSnooze(false);
  };

  const handleDismiss = () => {
    if (!suggestion) return;
    updateSuggestion.mutate({
      id: suggestion.id,
      input: { status: "dismissed" },
    });
  };

  const handleSend = async (message: string, channel: string, scheduledFor?: string) => {
    setError(null);
    try {
      if (channel === "telegram" && contact.telegram_username) {
        await sendMessage.mutateAsync({ contactId, message, channel, scheduledFor });
        setSent(
          scheduledFor
            ? `Scheduled for ${new Date(scheduledFor).toLocaleString()}`
            : "Sent via Telegram!"
        );
      } else if (channel === "email" && contact.emails?.length) {
        const email = contact.emails[0];
        const name = contact.given_name || contact.full_name || "";
        window.open(
          `mailto:${email}?subject=${encodeURIComponent(`Hey ${name}`.trim())}&body=${encodeURIComponent(message)}`,
          "_blank"
        );
        setSent("Email draft opened");
      } else if (channel === "twitter" && contact.twitter_handle) {
        window.open(
          `https://x.com/messages/compose?text=${encodeURIComponent(message)}`,
          "_blank"
        );
        void navigator.clipboard?.writeText(message).catch(() => {});
        setSent(
          `DM compose opened — search for @${contact.twitter_handle.replace(/^@/, "")}`
        );
      } else {
        void navigator.clipboard?.writeText(message).catch(() => {});
        setSent("Copied to clipboard");
      }
      if (suggestion) {
        updateSuggestion.mutate({
          id: suggestion.id,
          input: {
            status: "sent",
            suggested_message: message,
            suggested_channel: channel as "email" | "telegram" | "twitter",
          },
        });
      }
      setExpanded(false);
      void queryClient.invalidateQueries({ queryKey: ["interactions", contactId] });
      void queryClient.invalidateQueries({ queryKey: ["contacts", contactId] });
      void queryClient.invalidateQueries({ queryKey: ["contacts", "stats"] });
      void queryClient.invalidateQueries({ queryKey: ["contacts", "overdue"] });
      void queryClient.invalidateQueries({ queryKey: ["activity", "recent"] });
      setTimeout(() => setSent(null), 4000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send");
    }
  };

  return (
    <div
      className={cn(
        "bg-white rounded-xl border overflow-hidden transition-all",
        expanded
          ? hasSuggestion
            ? "border-amber-200 shadow-sm"
            : "border-teal-200 shadow-sm"
          : "border-stone-200"
      )}
    >
      {/* Collapsed header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-stone-50 transition-colors"
      >
        {hasSuggestion ? (
          <div className="w-8 h-8 rounded-full bg-amber-50 flex items-center justify-center shrink-0 mt-0.5">
            <Sparkles className="w-4 h-4 text-amber-500" />
          </div>
        ) : (
          <Send className="w-4 h-4 text-teal-500 shrink-0 mt-0.5" />
        )}
        <div className="flex-1 min-w-0">
          {sent ? (
            <span className="text-sm text-green-600 font-medium">{sent}</span>
          ) : hasSuggestion ? (
            <span className="text-sm text-stone-700 line-clamp-1">
              <span className="font-medium text-stone-900">Follow-up suggested</span>
              {!expanded && suggestion?.suggested_message && (
                <span className="text-stone-400">
                  {" "}
                  — {suggestion.suggested_message.slice(0, 60)}...
                </span>
              )}
            </span>
          ) : (
            <span className="text-sm text-stone-500">Write a message...</span>
          )}
        </div>
        <ChevronDown
          className={`w-4 h-4 text-stone-400 shrink-0 mt-0.5 transition-transform ${
            expanded ? "rotate-180" : ""
          }`}
        />
      </button>

      {/* Expanded editor */}
      {expanded && (
        <div
          className="px-4 pb-4 border-t border-stone-100 pt-3"
          onClick={(e) => e.stopPropagation()}
        >
          {sent && (
            <div className="text-xs text-green-700 bg-green-50 border border-green-200 rounded-md px-3 py-2 mb-3">
              {sent}
            </div>
          )}
          {error && (
            <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2 mb-3">
              {error}
            </div>
          )}
          <MessageEditor
            suggestionId={suggestion?.id}
            contactId={contactId}
            initialMessage={suggestion?.suggested_message ?? ""}
            initialChannel={suggestion?.suggested_channel}
            disabledChannels={disabledChannels}
            onSend={handleSend}
            autoFocus
          />
          {hasSuggestion && (
            <div className="flex items-center gap-2 mt-3">
              <div className="relative" ref={snoozeRef}>
                <button
                  onClick={() => setShowSnooze(!showSnooze)}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-md text-amber-600 border border-amber-200 bg-amber-50 hover:bg-amber-100 transition-colors"
                >
                  <Clock className="w-3 h-3" /> Snooze <ChevronDown className="w-2.5 h-2.5" />
                </button>
                {showSnooze && (
                  <div className="absolute left-0 bottom-full mb-1 w-32 bg-white rounded-lg border border-stone-200 shadow-lg py-1 z-50">
                    <button
                      onClick={() => handleSnooze(14)}
                      className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-stone-700 hover:bg-stone-50"
                    >
                      <Clock className="w-3 h-3 text-stone-400" /> 2 weeks
                    </button>
                    <button
                      onClick={() => handleSnooze(30)}
                      className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-stone-700 hover:bg-stone-50"
                    >
                      <Clock className="w-3 h-3 text-stone-400" /> 1 month
                    </button>
                    <button
                      onClick={() => handleSnooze(90)}
                      className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-stone-700 hover:bg-stone-50"
                    >
                      <Clock className="w-3 h-3 text-stone-400" /> 3 months
                    </button>
                  </div>
                )}
              </div>
              <button
                onClick={handleDismiss}
                className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-md text-stone-400 border border-stone-200 hover:bg-stone-50 transition-colors"
              >
                <X className="w-3 h-3" /> Dismiss
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
