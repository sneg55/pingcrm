"use client";

import { useState, type ReactNode } from "react";
import { Mail, MessageCircle, Twitter, RefreshCw, Send } from "lucide-react";
import { cn } from "@/lib/utils";
import { client } from "@/lib/api-client";

type Channel = "email" | "telegram" | "twitter";

interface ChannelConfig {
  label: string;
  icon: ReactNode;
  maxChars: number;
  color: string;
}

const channelConfig: Record<Channel, ChannelConfig> = {
  email: {
    label: "Email",
    icon: <Mail className="w-4 h-4" />,
    maxChars: 2000,
    color: "text-blue-600 bg-blue-50 border-blue-200",
  },
  telegram: {
    label: "Telegram",
    icon: <MessageCircle className="w-4 h-4" />,
    maxChars: 4096,
    color: "text-sky-600 bg-sky-50 border-sky-200",
  },
  twitter: {
    label: "Twitter/X",
    icon: <Twitter className="w-4 h-4" />,
    maxChars: 280,
    color: "text-slate-600 bg-slate-50 border-slate-200",
  },
};

interface MessageEditorProps {
  suggestionId?: string | null;
  contactId?: string;
  initialMessage?: string;
  initialChannel?: Channel;
  onSend?: (message: string, channel: Channel) => void;
  className?: string;
  disabledChannels?: Partial<Record<Channel, string>>;
}

export function MessageEditor({
  suggestionId,
  contactId,
  initialMessage = "",
  initialChannel,
  onSend,
  className,
  disabledChannels = {},
}: MessageEditorProps) {
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
  const [isRegenerating, setIsRegenerating] = useState(false);

  const config = channelConfig[channel] ?? channelConfig.email;
  const charCount = message.length;
  const isOverLimit = charCount > config.maxChars;

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
          "/api/v1/contacts/{contact_id}/compose" as any,
          {
            params: { path: { contact_id: contactId } },
            body: { channel },
          } as any,
        );
        msg = (data?.data as { suggested_message?: string })?.suggested_message;
      }
      if (msg) {
        setMessage(msg);
      }
    } catch {
      // Keep existing message if regeneration fails
    } finally {
      setIsRegenerating(false);
    }
  };

  const handleSend = () => {
    if (!message.trim() || isOverLimit) return;
    onSend?.(message.trim(), channel);
  };

  return (
    <div className={cn("space-y-3", className)}>
      {/* Channel selector */}
      <div className="flex gap-2">
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
              title={disabledReason ?? cfg.label}
              className={cn(
                "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border transition-colors",
                isDisabled
                  ? "text-gray-300 bg-gray-50 border-gray-100 cursor-not-allowed"
                  : isSelected
                    ? cfg.color
                    : "text-gray-500 bg-white border-gray-200 hover:bg-gray-50"
              )}
            >
              {cfg.icon}
              {cfg.label}
            </button>
          );
        })}
      </div>

      {/* Textarea */}
      <div className="relative">
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={4}
          className={cn(
            "w-full text-sm border rounded-md p-3 resize-none focus:outline-none focus:ring-2 focus:ring-blue-400 transition-colors",
            isOverLimit ? "border-red-300" : "border-gray-300"
          )}
          placeholder="Write a message..."
        />
        <span
          className={cn(
            "absolute bottom-2 right-2 text-xs",
            isOverLimit ? "text-red-500 font-medium" : "text-gray-400"
          )}
        >
          {charCount}/{config.maxChars}
        </span>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between">
        <button
          onClick={handleRegenerate}
          disabled={isRegenerating}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md text-gray-600 border border-gray-200 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <RefreshCw
            className={cn("w-4 h-4", isRegenerating && "animate-spin")}
          />
          Regenerate
        </button>

        <button
          onClick={handleSend}
          disabled={!message.trim() || isOverLimit}
          className="inline-flex items-center gap-1.5 px-4 py-1.5 text-sm font-medium rounded-md bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {channel === "telegram" ? (
            <><Send className="w-4 h-4" /> Send</>
          ) : channel === "email" ? (
            <><Mail className="w-4 h-4" /> Open Email</>
          ) : (
            <><Twitter className="w-4 h-4" /> Open Twitter</>
          )}
        </button>
      </div>
    </div>
  );
}
