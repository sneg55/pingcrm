import { cn } from "@/lib/utils";

type ScoreBadgeProps = {
  score: number;
  lastInteractionAt?: string | null;
  className?: string;
}

function getScoreVariant(score: number, lastInteractionAt?: string | null): {
  label: string;
  dotClass: string;
  textClass: string;
} {
  if (score >= 8) {
    return {
      label: "Strong",
      dotClass: "bg-emerald-500",
      textClass: "text-emerald-700 dark:text-emerald-400",
    };
  }
  if (score >= 4) {
    return {
      label: "Warm",
      dotClass: "bg-amber-400",
      textClass: "text-amber-700 dark:text-amber-400",
    };
  }
  // Score 0-3: check recency before labeling "Cold"
  if (lastInteractionAt) {
    const daysSince = (Date.now() - new Date(lastInteractionAt).getTime()) / (1000 * 60 * 60 * 24);
    if (daysSince <= 30) {
      return {
        label: "New",
        dotClass: "bg-sky-400",
        textClass: "text-sky-700 dark:text-sky-400",
      };
    }
  }
  return {
    label: "Cold",
    dotClass: "bg-red-400",
    textClass: "text-red-600 dark:text-red-400",
  };
}

export function ScoreBadge({ score, lastInteractionAt, className }: ScoreBadgeProps) {
  const { label, dotClass, textClass } = getScoreVariant(score, lastInteractionAt);

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 text-sm font-medium",
        textClass,
        className
      )}
      title={`Relationship score: ${score}/10`}
    >
      <span className={cn("w-2 h-2 rounded-full flex-shrink-0", dotClass)} />
      {label} <span className="font-mono-data">({score})</span>
    </span>
  );
}
