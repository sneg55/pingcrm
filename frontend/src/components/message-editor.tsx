"use client";

import { useState, useRef, useEffect } from "react";
import { Clock } from "lucide-react";
import { cn } from "@/lib/utils";
import { client } from "@/lib/api-client";
import { MessageEditorToolbar } from "./message-editor-toolbar";

type Channel = "email" | "telegram" | "twitter";

const channelMaxChars: Record<Channel, number> = {
  email: 2000,
  telegram: 4096,
  twitter: 280,
};

const allChannels = Object.keys(channelMaxChars) as Channel[];

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
  const availableChannels = allChannels.filter((ch) => !disabledChannels[ch]);
  const [channel, setChannel] = useState<Channel>(() => {
    if (initialChannel && initialChannel in channelMaxChars && !disabledChannels[initialChannel]) {
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

  const maxChars = channelMaxChars[channel] ?? channelMaxChars.email;
  const charCount = message.length;
  const isOverLimit = charCount > maxChars;
  const charPercent = Math.min((charCount / maxChars) * 100, 100);
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
      <MessageEditorToolbar
        channel={channel}
        onChannelChange={setChannel}
        disabledChannels={disabledChannels}
        isRegenerating={isRegenerating}
        onRegenerate={() => { void handleRegenerate(); }}
        showSchedule={showSchedule}
        onToggleSchedule={() => {
          setShowSchedule((v) => !v);
          if (showSchedule) setScheduledFor("");
        }}
        scheduledFor={scheduledFor}
        charCount={charCount}
        isOverLimit={isOverLimit}
        isSending={isSending}
        isRateLimited={isRateLimited}
        hasMessage={Boolean(message.trim())}
        onSend={() => { void handleSend(); }}
      />
    </div>
  );
}
