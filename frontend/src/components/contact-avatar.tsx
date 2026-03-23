"use client";

import { cn } from "@/lib/utils";

interface ContactAvatarProps {
  avatarUrl: string | null | undefined;
  name: string;
  size?: "xs" | "sm" | "md" | "lg";
  score?: number;
  className?: string;
}

const sizeClasses = {
  xs: "w-6 h-6 text-[10px]",
  sm: "w-8 h-8 text-xs",
  md: "w-10 h-10 text-sm",
  lg: "w-14 h-14 text-lg",
};

const ringClasses = {
  xs: "ring-[1.5px] ring-offset-1",
  sm: "ring-2 ring-offset-1",
  md: "ring-2 ring-offset-2",
  lg: "ring-[2.5px] ring-offset-2",
};

const avatarColors = [
  "bg-violet-100 dark:bg-violet-900 text-violet-700 dark:text-violet-300",
  "bg-teal-100 dark:bg-teal-900 text-teal-700 dark:text-teal-300",
  "bg-pink-100 dark:bg-pink-900 text-pink-700 dark:text-pink-300",
  "bg-orange-100 dark:bg-orange-900 text-orange-700 dark:text-orange-300",
  "bg-sky-100 dark:bg-sky-900 text-sky-700 dark:text-sky-300",
  "bg-indigo-100 dark:bg-indigo-900 text-indigo-700 dark:text-indigo-300",
  "bg-stone-200 dark:bg-stone-700 text-stone-600 dark:text-stone-300",
  "bg-emerald-100 dark:bg-emerald-900 text-emerald-700 dark:text-emerald-300",
];

function avatarColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return avatarColors[Math.abs(hash) % avatarColors.length];
}

function getScoreRingColor(score: number | undefined): string {
  if (score === undefined) return "";
  if (score >= 8) return "ring-emerald-400";
  if (score >= 4) return "ring-amber-400";
  return "ring-red-300";
}

export function ContactAvatar({
  avatarUrl,
  name,
  size = "md",
  score,
  className,
}: ContactAvatarProps) {
  const words = (name || "?").trim().split(/\s+/);
  const initial = words.length >= 2
    ? (words[0][0] + words[words.length - 1][0]).toUpperCase()
    : (words[0]?.[0] || "?").toUpperCase();
  const classes = sizeClasses[size];
  const scoreRing = score !== undefined
    ? `${ringClasses[size]} ${getScoreRingColor(score)}`
    : "";

  if (avatarUrl) {
    return (
      <img
        src={avatarUrl}
        alt={name}
        className={cn(
          classes,
          "rounded-full object-cover flex-shrink-0",
          scoreRing,
          className,
        )}
      />
    );
  }

  return (
    <div
      className={cn(
        classes,
        "rounded-full flex items-center justify-center font-semibold flex-shrink-0",
        avatarColor(name),
        scoreRing,
        className,
      )}
    >
      {initial}
    </div>
  );
}
