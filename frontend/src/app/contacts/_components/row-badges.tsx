"use client";

import { Mail, MessageCircle, Twitter } from "lucide-react";

export function ScoreNumberBadge({ score }: { score: number }) {
  let color = "bg-sky-50 dark:bg-sky-950 text-sky-700 dark:text-sky-400 border-sky-100 dark:border-sky-900";
  let dotColor = "bg-sky-400";
  if (score >= 8) { color = "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 border-emerald-100 dark:border-emerald-900"; dotColor = "bg-emerald-500"; }
  else if (score >= 4) { color = "bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-400 border-amber-100 dark:border-amber-900"; dotColor = "bg-amber-400"; }
  else if (score >= 1) { color = "bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-400 border-red-100 dark:border-red-900"; dotColor = "bg-red-400"; }

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border ${color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
      <span className="font-mono-data">{score}</span>
    </span>
  );
}

export function PriorityBadge({ level }: { level: string }) {
  const icons: Record<string, string> = { high: "🔥", medium: "⚡", low: "💤" };
  const icon = icons[level];
  if (!icon) return <span className="text-stone-300 dark:text-stone-600">&mdash;</span>;
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-400 border border-red-100 dark:border-red-900">
      {icon}
    </span>
  );
}

export function PlatformIcons({ emails, telegram, twitter }: { emails: string[]; telegram?: string | null; twitter?: string | null }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {emails.length > 0 && <span className="text-red-400" aria-label="Email"><Mail className="w-3 h-3" /></span>}
      {telegram && <span className="text-sky-400" aria-label="Telegram"><MessageCircle className="w-3 h-3" /></span>}
      {twitter && <span className="text-stone-400 dark:text-stone-500" aria-label="Twitter/X"><Twitter className="w-3 h-3" /></span>}
    </span>
  );
}

export function DaysAgo({ dateStr }: { dateStr?: string | null }) {
  if (!dateStr) return <span className="text-stone-300 dark:text-stone-600">&mdash;</span>;
  const days = Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000);
  const isOverdue = days > 30;
  return (
    <span className={`font-mono-data text-xs ${isOverdue ? "font-medium text-red-500" : "text-stone-500 dark:text-stone-400"}`}>
      {days}d
    </span>
  );
}
