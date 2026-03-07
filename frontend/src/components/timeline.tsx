"use client";

import { formatDistanceToNow } from "date-fns";
import { Mail, MessageCircle, Twitter, FileText, Plus, Calendar, Linkedin } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

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
  className?: string;
}

const platformIcons: Record<TimelineEntry["platform"], React.ReactNode> = {
  email: <Mail className="w-4 h-4" />,
  telegram: <MessageCircle className="w-4 h-4" />,
  twitter: <Twitter className="w-4 h-4" />,
  linkedin: <Linkedin className="w-4 h-4" />,
  manual: <FileText className="w-4 h-4" />,
  meeting: <Calendar className="w-4 h-4" />,
};

const platformColors: Record<TimelineEntry["platform"], string> = {
  email: "bg-blue-100 text-blue-600",
  telegram: "bg-sky-100 text-sky-600",
  twitter: "bg-slate-100 text-slate-600",
  linkedin: "bg-blue-100 text-blue-700",
  manual: "bg-gray-100 text-gray-600",
  meeting: "bg-purple-100 text-purple-600",
};

export function Timeline({ interactions, onAddNote, className }: TimelineProps) {
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
        <h2 className="text-lg font-semibold text-gray-900">Interactions</h2>
        <button
          onClick={() => setShowNoteInput((v) => !v)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md bg-blue-600 text-white hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add note
        </button>
      </div>

      {showNoteInput && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 space-y-2">
          <textarea
            className="w-full text-sm border border-gray-300 rounded-md p-2 resize-none focus:outline-none focus:ring-2 focus:ring-blue-400"
            rows={3}
            placeholder="Write a note..."
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
          />
          <div className="flex gap-2 justify-end">
            <button
              onClick={() => setShowNoteInput(false)}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmitNote}
              className="text-sm px-3 py-1 rounded-md bg-blue-600 text-white hover:bg-blue-700"
            >
              Save
            </button>
          </div>
        </div>
      )}

      {interactions.length === 0 ? (
        <p className="text-sm text-gray-400 py-6 text-center">
          No interactions yet. Add a note to get started.
        </p>
      ) : (
        <ol className="relative border-l border-gray-200 space-y-6 pl-4">
          {interactions.map((item) => (
            <li key={item.id} className="ml-2">
              <span
                className={cn(
                  "absolute -left-3 flex h-6 w-6 items-center justify-center rounded-full",
                  platformColors[item.platform]
                )}
              >
                {platformIcons[item.platform]}
              </span>
              <div className="ml-4">
                <p className="text-xs text-gray-400 mb-0.5">
                  {item.platform} &middot;{" "}
                  {formatDistanceToNow(new Date(item.occurred_at), {
                    addSuffix: true,
                  })}
                </p>
                {item.content_preview && (
                  <p className="text-sm text-gray-700">{item.content_preview}</p>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
