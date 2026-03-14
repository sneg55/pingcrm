"use client";

import { formatDistanceToNow } from "date-fns";
import { Mail, MessageCircle, Twitter, FileText, Plus, Calendar, Linkedin } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

const URL_RE = /(https?:\/\/[^\s<]+)/g;
const URL_TEST = /^https?:\/\/[^\s<]+$/;

function Linkify({ text, className }: { text: string; className?: string }) {
  const parts = text.split(URL_RE);
  return (
    <span>
      {parts.map((part, i) =>
        URL_TEST.test(part) ? (
          <a
            key={i}
            href={part}
            target="_blank"
            rel="noopener noreferrer"
            className={cn("underline break-all", className)}
          >
            {part}
          </a>
        ) : (
          part
        )
      )}
    </span>
  );
}

export interface TimelineEntry {
  id: string;
  platform: "email" | "telegram" | "twitter" | "linkedin" | "manual" | "meeting";
  direction: "inbound" | "outbound" | "mutual";
  content_preview: string | null;
  occurred_at: string;
}

interface TimelineProps {
  interactions: TimelineEntry[];
  onAddNote?: (content: string) => void;
  contactName?: string;
  className?: string;
}

const platformIcons: Record<TimelineEntry["platform"], React.ReactNode> = {
  email: <Mail className="w-3.5 h-3.5" />,
  telegram: <MessageCircle className="w-3.5 h-3.5" />,
  twitter: <Twitter className="w-3.5 h-3.5" />,
  linkedin: <Linkedin className="w-3.5 h-3.5" />,
  manual: <FileText className="w-3.5 h-3.5" />,
  meeting: <Calendar className="w-3.5 h-3.5" />,
};

const platformColors: Record<TimelineEntry["platform"], string> = {
  email: "bg-teal-500",
  telegram: "bg-sky-500",
  twitter: "bg-slate-600",
  linkedin: "bg-blue-600",
  manual: "bg-amber-500",
  meeting: "bg-violet-500",
};

export function Timeline({ interactions, onAddNote, contactName, className }: TimelineProps) {
  const [noteText, setNoteText] = useState("");
  const [showNoteInput, setShowNoteInput] = useState(false);

  const handleSubmitNote = () => {
    if (!noteText.trim()) return;
    onAddNote?.(noteText.trim());
    setNoteText("");
    setShowNoteInput(false);
  };

  return (
    <div className={cn("space-y-4", className)}>
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-display font-semibold text-stone-900">Interactions</h2>
        <button
          onClick={() => setShowNoteInput((v) => !v)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md bg-teal-600 text-white hover:bg-teal-700 transition-colors btn-press"
        >
          <Plus className="w-4 h-4" />
          Add note
        </button>
      </div>

      {showNoteInput && (
        <div className="rounded-lg border border-teal-200 bg-teal-50 p-3 space-y-2">
          <textarea
            className="w-full text-sm border border-stone-300 rounded-md p-2 resize-none focus:outline-none focus:ring-2 focus:ring-teal-400"
            rows={3}
            placeholder="Write a note..."
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
          />
          <div className="flex gap-2 justify-end">
            <button
              onClick={() => setShowNoteInput(false)}
              className="text-sm text-stone-500 hover:text-stone-700"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmitNote}
              className="text-sm px-3 py-1 rounded-md bg-teal-600 text-white hover:bg-teal-700 btn-press"
            >
              Save
            </button>
          </div>
        </div>
      )}

      {interactions.length === 0 ? (
        <div className="text-center py-8">
          <MessageCircle className="w-10 h-10 text-stone-200 mx-auto mb-2 animate-float" />
          <p className="text-sm text-stone-400">
            No interactions yet. Add a note to get started.
          </p>
        </div>
      ) : (
        <div className="relative">
          {/* Vertical connector line */}
          <div className="absolute left-5 top-3 bottom-3 w-px bg-stone-200" />

          <div className="space-y-3">
            {interactions.map((item, idx) => {
              const isManual = item.platform === "manual";
              const isOutbound = item.direction === "outbound";
              const isMutual = item.direction === "mutual";
              const authorLabel = isOutbound
                ? "You"
                : isMutual
                  ? "Both"
                  : contactName || "Contact";

              if (isManual) {
                return (
                  <div
                    key={item.id}
                    className="relative pl-12 animate-fade-in-up"
                    style={{ animationDelay: `${idx * 30}ms` }}
                  >
                    {/* Timeline dot */}
                    <div className="absolute left-3.5 top-3.5 w-3 h-3 rounded-full bg-amber-400 border-2 border-white z-10" />
                    <div className="border border-amber-200 bg-amber-50 rounded-lg px-4 py-3">
                      <div className="flex items-center gap-1.5 mb-1 text-amber-500">
                        <FileText className="w-3.5 h-3.5" />
                        <span className="text-xs font-medium">Note</span>
                        <span className="text-xs">
                          &middot;{" "}
                          {formatDistanceToNow(new Date(item.occurred_at), {
                            addSuffix: true,
                          })}
                        </span>
                      </div>
                      {item.content_preview && (
                        <p className="text-sm text-amber-900 leading-relaxed">
                          <Linkify text={item.content_preview} className="text-amber-700 hover:text-amber-900" />
                        </p>
                      )}
                    </div>
                  </div>
                );
              }

              return (
                <div
                  key={item.id}
                  className="relative pl-12 animate-fade-in-up"
                  style={{ animationDelay: `${idx * 30}ms` }}
                >
                  {/* Timeline dot with platform color */}
                  <div className={cn(
                    "absolute left-3.5 top-3.5 w-3 h-3 rounded-full border-2 border-white z-10",
                    platformColors[item.platform]
                  )} />
                  <div
                    className={cn(
                      "flex",
                      isOutbound ? "justify-end" : "justify-start"
                    )}
                  >
                    <div
                      className={cn(
                        "max-w-[85%] rounded-2xl px-4 py-2.5",
                        isOutbound
                          ? "bg-teal-600 text-white rounded-br-md"
                          : "bg-stone-100 text-stone-900 rounded-bl-md"
                      )}
                    >
                      <div className={cn(
                        "flex items-center gap-1.5 mb-1",
                        isOutbound ? "text-teal-100" : "text-stone-400"
                      )}>
                        <span className="flex-shrink-0">{platformIcons[item.platform]}</span>
                        <span className="text-xs font-medium">
                          {authorLabel}
                        </span>
                        <span className="text-xs">
                          &middot; {item.platform} &middot;{" "}
                          {formatDistanceToNow(new Date(item.occurred_at), {
                            addSuffix: true,
                          })}
                        </span>
                      </div>
                      {item.content_preview && (
                        <p className={cn(
                          "text-sm leading-relaxed",
                          isOutbound ? "text-white" : "text-stone-700"
                        )}>
                          <Linkify
                            text={item.content_preview}
                            className={isOutbound ? "text-teal-100 hover:text-white" : "text-teal-600 hover:text-teal-800"}
                          />
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
