import { cn } from "@/lib/utils";

interface ScoreBadgeProps {
  score: number;
  className?: string;
}

function getScoreVariant(score: number): {
  label: string;
  dotClass: string;
  textClass: string;
} {
  if (score >= 8) {
    return {
      label: "Strong",
      dotClass: "bg-green-500",
      textClass: "text-green-700",
    };
  }
  if (score >= 4) {
    return {
      label: "Active",
      dotClass: "bg-yellow-400",
      textClass: "text-yellow-700",
    };
  }
  return {
    label: "Dormant",
    dotClass: "bg-red-400",
    textClass: "text-red-700",
  };
}

export function ScoreBadge({ score, className }: ScoreBadgeProps) {
  const { label, dotClass, textClass } = getScoreVariant(score);

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
      {label} ({score})
    </span>
  );
}
