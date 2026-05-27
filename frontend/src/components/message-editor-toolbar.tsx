"use client";

import { type ReactNode } from "react";
import { RefreshCw, Send, Clock, Twitter, Mail, MessageCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type Channel = "email" | "telegram" | "twitter";

type ChannelConfig = {
  label: string;
  icon: ReactNode;
  maxChars: number;
  activeColor: string;
};

const channelConfig: Record<Channel, ChannelConfig> = {
  email: {
    label: "Email",
    icon: <Mail className="w-4 h-4" />,
    maxChars: 2000,
    activeColor: "text-blue-500 dark:text-blue-400",
  },
  telegram: {
    label: "Telegram",
    icon: <MessageCircle className="w-4 h-4" />,
    maxChars: 4096,
    activeColor: "text-sky-500 dark:text-sky-400",
  },
  twitter: {
    label: "Twitter/X",
    icon: <Twitter className="w-4 h-4" />,
    maxChars: 280,
    activeColor: "text-stone-600 dark:text-stone-300",
  },
};

type ChannelButtonProps = {
  ch: Channel;
  isSelected: boolean;
  disabledReason: string | undefined;
  onChannelChange: (ch: Channel) => void;
};

function ChannelButton({ ch, isSelected, disabledReason, onChannelChange }: ChannelButtonProps) {
  const cfg = channelConfig[ch];
  const isDisabled = Boolean(disabledReason);
  return (
    <button
      key={ch}
      onClick={() => !isDisabled && onChannelChange(ch)}
      disabled={isDisabled}
      title={isDisabled ? disabledReason : `Send via ${cfg.label}`}
      className={cn(
        "p-1.5 rounded-md transition-colors",
        isDisabled
          ? "text-stone-300 dark:text-stone-700 cursor-not-allowed"
          : isSelected
            ? cn(cfg.activeColor, "bg-stone-100 dark:bg-stone-800")
            : "text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
      )}
    >
      {cfg.icon}
    </button>
  );
}

function getSendIcon(isSending: boolean, showSchedule: boolean, scheduledFor: string): ReactNode {
  if (isSending) return <RefreshCw className="w-4 h-4 animate-spin" />;
  if (showSchedule && scheduledFor) return <Clock className="w-4 h-4" />;
  return <Send className="w-4 h-4" />;
}

type SendButtonState = { hasMessage: boolean; isOverLimit: boolean; isSending: boolean; showSchedule: boolean; scheduledFor: string };
function getSendButtonColor({ hasMessage, isOverLimit, isSending, showSchedule, scheduledFor }: SendButtonState): string {
  if (hasMessage && !isOverLimit && !isSending) {
    return showSchedule && scheduledFor
      ? "bg-sky-500 text-white hover:bg-sky-600"
      : "bg-teal-500 text-white hover:bg-teal-600";
  }
  return "bg-stone-200 dark:bg-stone-700 text-stone-400 dark:text-stone-500";
}

export type MessageEditorToolbarProps = {
  channel: Channel;
  onChannelChange: (ch: Channel) => void;
  disabledChannels: Partial<Record<Channel, string>>;
  isRegenerating: boolean;
  onRegenerate: () => void;
  showSchedule: boolean;
  onToggleSchedule: () => void;
  scheduledFor: string;
  charCount: number;
  isOverLimit: boolean;
  isSending: boolean;
  isRateLimited: boolean;
  hasMessage: boolean;
  onSend: () => void;
};

export function MessageEditorToolbar({
  channel,
  onChannelChange,
  disabledChannels,
  isRegenerating,
  onRegenerate,
  showSchedule,
  onToggleSchedule,
  scheduledFor,
  charCount,
  isOverLimit,
  isSending,
  isRateLimited,
  hasMessage,
  onSend,
}: MessageEditorToolbarProps) {
  const config = channelConfig[channel] ?? channelConfig.email;
  const sendButtonColor = getSendButtonColor({ hasMessage, isOverLimit, isSending, showSchedule, scheduledFor });
  const sendIcon = getSendIcon(isSending, showSchedule, scheduledFor);

  return (
    <div className="flex items-center justify-between mt-2 pt-2 border-t border-stone-100 dark:border-stone-800">
      {/* Left: icon actions */}
      <div className="flex items-center gap-1">
        {/* Channel selector icons */}
        {(Object.keys(channelConfig) as Channel[]).map((ch) => (
          <ChannelButton
            key={ch}
            ch={ch}
            isSelected={channel === ch}
            disabledReason={disabledChannels[ch]}
            onChannelChange={onChannelChange}
          />
        ))}

        {/* Divider */}
        <div className="w-px h-4 bg-stone-200 dark:bg-stone-700 mx-1" />

        {/* Regenerate */}
        <button
          onClick={onRegenerate}
          disabled={isRegenerating}
          title="Regenerate message"
          className="p-1.5 rounded-md text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <RefreshCw className={cn("w-4 h-4", isRegenerating && "animate-spin")} />
        </button>
      </div>

      {/* Right: schedule + char count + send */}
      <div className="flex items-center gap-2">
        {/* Schedule (Telegram only) */}
        {channel === "telegram" && (
          <button
            onClick={onToggleSchedule}
            title={showSchedule ? "Cancel schedule" : "Schedule send"}
            className={cn(
              "p-1.5 rounded-md transition-colors",
              showSchedule
                ? "text-sky-500 dark:text-sky-400 bg-sky-50 dark:bg-sky-950"
                : "text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
            )}
          >
            <Clock className="w-4 h-4" />
          </button>
        )}
        {charCount > 0 && (
          <span
            className={cn(
              "text-xs tabular-nums",
              isOverLimit ? "text-red-500 font-medium" : "text-stone-400 dark:text-stone-500"
            )}
          >
            {charCount}/{config.maxChars}
          </span>
        )}
        <button
          onClick={onSend}
          disabled={!hasMessage || isOverLimit || isSending || isRateLimited || (showSchedule && !scheduledFor)}
          className={cn(
            "inline-flex items-center justify-center w-8 h-8 rounded-full transition-colors disabled:opacity-30 disabled:cursor-not-allowed",
            sendButtonColor
          )}
          title={showSchedule && scheduledFor ? "Schedule" : "Send"}
        >
          {sendIcon}
        </button>
      </div>
    </div>
  );
}
