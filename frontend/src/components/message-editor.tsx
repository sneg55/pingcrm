"use client";

import { useState, type ReactNode } from "react";
import { Mail, MessageCircle, Twitter, RefreshCw, Send } from "lucide-react";
import { cn } from "@/lib/utils";
import apiClient from "@/lib/api";

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
  suggestionId: string;
  initialMessage: string;
  initialChannel: Channel;
  onSend?: (message: string, channel: Channel) => void;
  className?: string;
}

export function MessageEditor({
  suggestionId,
  initialMessage,
  initialChannel,
  onSend,
  className,
}: MessageEditorProps) {
  const [message, setMessage] = useState(initialMessage);
  const [channel, setChannel] = useState<Channel>(initialChannel);
  const [isRegenerating, setIsRegenerating] = useState(false);

  const config = channelConfig[channel];
  const charCount = message.length;
  const isOverLimit = charCount > config.maxChars;

  const handleRegenerate = async () => {
    setIsRegenerating(true);
    try {
      const { data } = await apiClient.post<{
        data: { suggested_message: string };
        error: string | null;
      }>(`/suggestions/${suggestionId}/regenerate`, { channel });
      if (data.data?.suggested_message) {
        setMessage(data.data.suggested_message);
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
          return (
            <button
              key={ch}
              onClick={() => setChannel(ch)}
              className={cn(
                "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border transition-colors",
                isSelected
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
          placeholder="Your message..."
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
          <Send className="w-4 h-4" />
          Send
        </button>
      </div>
    </div>
  );
}
