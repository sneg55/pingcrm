"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  useUpdateSuggestion,
  useSendMessage,
} from "@/hooks/use-suggestions";
import type { Contact } from "@/hooks/use-contacts";

interface UseSendMessageHandlerOptions {
  contact: Contact;
  contactId: string;
  suggestionId?: string;
  onSent: (message: string) => void;
  onError: (message: string) => void;
  onSuccess: () => void;
}

export function useSendMessageHandler({
  contact,
  contactId,
  suggestionId,
  onSent,
  onError,
  onSuccess,
}: UseSendMessageHandlerOptions) {
  const updateSuggestion = useUpdateSuggestion();
  const sendMessage = useSendMessage();
  const queryClient = useQueryClient();

  return async (message: string, channel: string, scheduledFor?: string) => {
    onError("");
    try {
      if (channel === "telegram" && contact.telegram_username) {
        await sendMessage.mutateAsync({ contactId, message, channel, scheduledFor });
        onSent(
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
        onSent("Email draft opened");
      } else if (channel === "twitter" && contact.twitter_handle) {
        window.open(
          `https://x.com/messages/compose?text=${encodeURIComponent(message)}`,
          "_blank"
        );
        void navigator.clipboard?.writeText(message).catch((err: unknown) => {
          console.error("clipboard write failed", err);
        });
        onSent(
          `DM compose opened — search for @${contact.twitter_handle.replace(/^@/, "")}`
        );
      } else {
        void navigator.clipboard?.writeText(message).catch((err: unknown) => {
          console.error("clipboard write failed", err);
        });
        onSent("Copied to clipboard");
      }
      if (suggestionId) {
        updateSuggestion.mutate({
          id: suggestionId,
          input: {
            status: "sent",
            suggested_message: message,
            suggested_channel: channel as "email" | "telegram" | "twitter",
          },
        });
      }
      onSuccess();
      void queryClient.invalidateQueries({ queryKey: ["interactions", contactId] });
      void queryClient.invalidateQueries({ queryKey: ["contacts", contactId] });
      void queryClient.invalidateQueries({ queryKey: ["contacts", "stats"] });
      void queryClient.invalidateQueries({ queryKey: ["contacts", "overdue"] });
      void queryClient.invalidateQueries({ queryKey: ["activity", "recent"] });
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to send");
    }
  };
}
