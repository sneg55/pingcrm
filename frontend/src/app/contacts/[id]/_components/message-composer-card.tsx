"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { MessageEditor } from "@/components/message-editor";
import { useContactSuggestion } from "@/hooks/use-suggestions";
import type { Contact } from "@/hooks/use-contacts";
import { SuggestionActions } from "./suggestion-actions";
import { useSendMessageHandler } from "./use-send-message-handler";
import { ComposerHeader } from "./composer-header";

export function MessageComposerCard({
  contact,
  contactId,
}: {
  contact: Contact;
  contactId: string;
}) {
  const suggestion = useContactSuggestion(contactId);
  const [expanded, setExpanded] = useState(false);
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [flashSuccess, setFlashSuccess] = useState(false);

  const hasSuggestion = Boolean(suggestion);

  const disabledChannels = {
    ...(!contact.emails?.length ? { email: "No email" as const } : {}),
    ...(!contact.telegram_username ? { telegram: "No Telegram" as const } : {}),
    ...(!contact.twitter_handle ? { twitter: "No Twitter" as const } : {}),
  };

  const handleSend = useSendMessageHandler({
    contact,
    contactId,
    suggestionId: suggestion?.id,
    onSent(msg) {
      setSent(msg);
      setTimeout(() => setSent(null), 4000);
    },
    onError(msg) {
      setError(msg || null);
    },
    onSuccess() {
      setFlashSuccess(true);
      setTimeout(() => setFlashSuccess(false), 1000);
      setExpanded(false);
    },
  });

  return (
    <div
      className={cn(
        "bg-white dark:bg-stone-900 rounded-xl border overflow-hidden transition-all",
        expanded
          ? hasSuggestion
            ? "border-amber-200 dark:border-amber-800 shadow-sm"
            : "border-teal-200 dark:border-teal-800 shadow-sm"
          : "border-stone-200 dark:border-stone-700",
        flashSuccess && "flash-success"
      )}
    >
      <ComposerHeader
        hasSuggestion={hasSuggestion}
        expanded={expanded}
        sent={sent}
        suggestedMessage={suggestion?.suggested_message}
        onClick={() => setExpanded(!expanded)}
      />

      {/* Expanded editor */}
      {expanded && (
        <div
          className="px-4 pb-3 border-t border-stone-100 dark:border-stone-800 pt-3"
          onClick={(e) => e.stopPropagation()}
        >
          {sent && (
            <div className="text-xs text-green-700 bg-green-50 border border-green-200 rounded-md px-3 py-2 mb-3">
              {sent}
            </div>
          )}
          {error && (
            <div className="text-xs text-red-700 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-md px-3 py-2 mb-3">
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
          {/* Suggestion actions: snooze + dismiss — compact inline */}
          {hasSuggestion && suggestion && (
            <SuggestionActions suggestionId={suggestion.id} />
          )}
        </div>
      )}
    </div>
  );
}
