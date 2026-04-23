"use client";

import { useState, useRef, useEffect, type ReactNode } from "react";
import { Mail, MessageCircle, Twitter, RefreshCw, Send, Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import { client } from "@/lib/api-client";

type Channel = "email" | "telegram" | "twitter";

type ChannelConfig = {
  label: string;
  icon: ReactNode;
  maxChars: number;
  activeColor: string;
}

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

type MessageEditorProps = {
  suggestionId?: string | null;
  contactId?: string;
  initialMessage?: string;
  initialChannel?: Channel;
  onSend?: (message: string, channel: Channel, scheduledFor?: string) => void | Promise<void>;
  onRegenerate?: (message: string, channel: Channel) => void;
  className?: string;
  disabledChannels?: Partial<Record<Channel, string>>;
  autoFocus?: boolean;
}

// eslint-disable-next-line sonarjs/cognitive-complexity -- editor coordinates channel toggles, send states, tone analysis, and disabled-channel hints; refactor tracked separately
export function MessageEditor({
  suggestionId,
  contactId,
  initialMessage = "",
  initialChannel,
  onSend,
  onRegenerate,
  className,
  disabledChannels = {},
  autoFocus = false,
}: MessageEditorProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [message, setMessage] = useState(initialMessage);
  const availableChannels = (Object.keys(channelConfig) as Channel[]).filter(
    (ch) => !disabledChannels[ch]
  );
  const [channel, setChannel] = useState<Channel>(() => {
    if (initialChannel && initialChannel in channelConfig && !disabledChannels[initialChannel]) {
      return initialChannel;
    }
    return availableChannels[0] ?? "email";
  });
  const [isSending, setIsSending] = useState(false);
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);
  const [scheduledFor, setScheduledFor] = useState("");
  const [rateLimitEnd, setRateLimitEnd] = useState<number | null>(null);
  const [rateLimitRemaining, setRateLimitRemaining] = useState(0);

  const config = channelConfig[channel] ?? channelConfig.email;
  const charCount = message.length;
  const isOverLimit = charCount > config.maxChars;
  const charPercent = Math.min((charCount / config.maxChars) * 100, 100);
  const isRateLimited = rateLimitEnd !== null && rateLimitRemaining > 0;

  useEffect(() => {
    if (autoFocus) textareaRef.current?.focus();
  }, [autoFocus]);

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.max(80, el.scrollHeight)}px`;
  }, [message]);

  // Countdown timer for rate limit
  useEffect(() => {
    if (!rateLimitEnd) return;
    const tick = () => {
      const remaining = Math.max(0, Math.ceil((rateLimitEnd - Date.now()) / 1000));
      setRateLimitRemaining(remaining);
      if (remaining <= 0) setRateLimitEnd(null);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [rateLimitEnd]);

  const handleRegenerate = async () => {
    setIsRegenerating(true);
    try {
      let msg: string | undefined;
      if (suggestionId) {
        const { data } = await client.POST(
          "/api/v1/suggestions/{suggestion_id}/regenerate",
          {
            params: { path: { suggestion_id: suggestionId } },
            body: { channel },
          }
        );
        msg = (data?.data as { suggested_message?: string })?.suggested_message;
      } else if (contactId) {
        const { data } = await client.POST(
          "/api/v1/contacts/{contact_id}/compose",
          {
            params: { path: { contact_id: contactId } },
            body: { channel },
          },
        );
        msg = (data?.data as { suggested_message?: string })?.suggested_message;
      }
      if (msg) {
        setMessage(msg);
        onRegenerate?.(msg, channel);
      }
    } catch {
      // Keep existing message if regeneration fails
    } finally {
      setIsRegenerating(false);
    }
  };

  const handleSend = async () => {
    if (!message.trim() || isOverLimit || isSending || isRateLimited) return;
    const iso = scheduledFor ? new Date(scheduledFor).toISOString() : undefined;
    setIsSending(true);
    try {
      await onSend?.(message.trim(), channel, iso);
    } catch (err: unknown) {
      if (err && typeof err === "object" && "status" in err && (err as { status: number }).status === 429) {
        const body = "body" in err ? (err as { body: { meta?: { retry_after?: number } } }).body : undefined;
        const retryAfter = body?.meta?.retry_after ?? 3600;
        setRateLimitEnd(Date.now() + retryAfter * 1000);
      }
    } finally {
      setIsSending(false);
    }
  };

  return (
    <div className={cn("space-y-0", className)}>
      {/* Textarea — borderless, auto-resize */}
      <textarea
        ref={textareaRef}
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        rows={2}
        className="w-full text-sm bg-transparent border-0 p-0 resize-none focus:outline-none focus:ring-0 text-stone-900 dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
        placeholder="Write a message..."
      />

      {/* Character limit bar */}
      {charCount > 0 && (
        <div className="h-0.5 w-full bg-stone-100 dark:bg-stone-800 rounded-full overflow-hidden mt-2">
          <div
            className={cn(
              "h-full transition-all duration-150 rounded-full",
              isOverLimit ? "bg-red-500" : charPercent > 80 ? "bg-amber-400" : "bg-teal-400"
            )}
            style={{ width: `${Math.min(charPercent, 100)}%` }}
          />
        </div>
      )}

      {/* Schedule datetime picker (inline, when active) */}
      {showSchedule && channel === "telegram" && (
        <div className="mt-2 pt-2 border-t border-stone-100 dark:border-stone-800 space-y-1.5">
          <div className="flex items-center gap-2">
            <Clock className="w-3.5 h-3.5 text-sky-500 shrink-0" />
            <input
              type="datetime-local"
              value={scheduledFor}
              onChange={(e) => setScheduledFor(e.target.value)}
              min={new Date(Date.now() + 60000).toISOString().slice(0, 16)}
              className="flex-1 text-xs border border-stone-200 dark:border-stone-700 rounded-md px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-sky-400 bg-transparent text-stone-900 dark:text-stone-100"
            />
            <button
              onClick={() => { setShowSchedule(false); setScheduledFor(""); }}
              className="text-xs text-stone-400 hover:text-stone-600 dark:hover:text-stone-300"
            >
              Cancel
            </button>
          </div>
          <p className="text-xs text-stone-400 dark:text-stone-500">
            Uses Telegram native scheduling. Edit or cancel from the Telegram app.
          </p>
        </div>
      )}

      {/* Rate limit banner */}
      {isRateLimited && (
        <div className="flex items-center gap-2 px-3 py-1.5 mt-2 text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-md">
          <Clock className="w-3.5 h-3.5 shrink-0" />
          Rate limited — retry in {rateLimitRemaining >= 60 ? `${Math.ceil(rateLimitRemaining / 60)}m` : `${rateLimitRemaining}s`}
        </div>
      )}

      {/* Toolbar — Twitter-style: icons left, char count + send right */}
      <div className="flex items-center justify-between mt-2 pt-2 border-t border-stone-100 dark:border-stone-800">
        {/* Left: icon actions */}
        <div className="flex items-center gap-1">
          {/* Channel selector icons */}
          {(Object.keys(channelConfig) as Channel[]).map((ch) => {
            const cfg = channelConfig[ch];
            const isSelected = channel === ch;
            const disabledReason = disabledChannels[ch];
            const isDisabled = Boolean(disabledReason);
            return (
              <button
                key={ch}
                onClick={() => !isDisabled && setChannel(ch)}
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
          })}

          {/* Divider */}
          <div className="w-px h-4 bg-stone-200 dark:bg-stone-700 mx-1" />

          {/* Regenerate */}
          <button
            onClick={() => { void handleRegenerate(); }}
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
              onClick={() => {
                setShowSchedule((v) => !v);
                if (showSchedule) setScheduledFor("");
              }}
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
            onClick={() => { void handleSend(); }}
            disabled={!message.trim() || isOverLimit || isSending || isRateLimited || (showSchedule && !scheduledFor)}
            className={cn(
              "inline-flex items-center justify-center w-8 h-8 rounded-full transition-colors disabled:opacity-30 disabled:cursor-not-allowed",
              message.trim() && !isOverLimit && !isSending
                ? showSchedule && scheduledFor
                  ? "bg-sky-500 text-white hover:bg-sky-600"
                  : "bg-teal-500 text-white hover:bg-teal-600"
                : "bg-stone-200 dark:bg-stone-700 text-stone-400 dark:text-stone-500"
            )}
            title={showSchedule && scheduledFor ? "Schedule" : "Send"}
          >
            {isSending ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : showSchedule && scheduledFor ? (
              <Clock className="w-4 h-4" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
