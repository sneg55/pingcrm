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
        "rounded-full bg-gradient-to-br from-teal-500 to-cyan-600 flex items-center justify-center text-white font-semibold flex-shrink-0",
        scoreRing,
        className,
      )}
    >
      {initial}
    </div>
  );
}
