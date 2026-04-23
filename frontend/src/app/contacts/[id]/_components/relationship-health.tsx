import { formatDistanceToNow, format } from "date-fns";
import { cn } from "@/lib/utils";
import type { Contact, ActivityData } from "@/hooks/use-contacts";
import { scorePillClasses } from "../_lib/formatters";

export function RelationshipHealth({
  activityData,
  contact,
}: {
  activityData: ActivityData;
  contact: Contact;
}) {
  const { dimensions, stats } = activityData;
  const score = contact.relationship_score;
  const s = scorePillClasses(score);

  return (
    <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">Relationship Health</h3>
        <span className={cn("font-mono text-lg font-bold", s.text)}>
          {score}
          <span className="text-stone-300 dark:text-stone-600 font-normal text-sm">/10</span>
        </span>
      </div>

      <div className="space-y-2.5 mb-5">
        {[
          { label: "Reciprocity", ...dimensions.reciprocity },
          { label: "Recency", ...dimensions.recency },
          { label: "Frequency", ...dimensions.frequency },
          { label: "Breadth", ...dimensions.breadth },
          ...(dimensions.tenure ? [{ label: "Tenure", ...dimensions.tenure }] : []),
        ].map((dim) => (
          <div key={dim.label}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-stone-600 dark:text-stone-300">{dim.label}</span>
              <span className="font-mono text-[11px] text-stone-400 dark:text-stone-500">
                {dim.value}/{dim.max}
              </span>
            </div>
            <div className="h-1.5 bg-stone-100 dark:bg-stone-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-teal-500 rounded-full transition-all"
                style={{ width: dim.max > 0 ? `${(dim.value / dim.max) * 100}%` : "0%" }}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="border-t border-stone-100 dark:border-stone-800 pt-4 space-y-2.5">
        <div className="flex items-center justify-between">
          <span className="text-xs text-stone-500 dark:text-stone-400">Last contacted</span>
          <div className="text-right">
            <span className="text-xs font-medium text-stone-900 dark:text-stone-100">
              {contact.last_interaction_at
                ? formatDistanceToNow(new Date(contact.last_interaction_at), { addSuffix: true })
                : "Never"}
            </span>
            {stats.platforms.length > 0 && (
              <span className="text-[10px] text-stone-400 dark:text-stone-500 ml-1">via {stats.platforms[0]}</span>
            )}
          </div>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-stone-500 dark:text-stone-400">Total interactions</span>
          <div className="text-right">
            <span className="text-xs font-medium text-stone-900 dark:text-stone-100">{stats.interaction_count}</span>
            {(stats.inbound_365d > 0 || stats.outbound_365d > 0) && (
              <span className="text-[10px] text-stone-400 dark:text-stone-500 ml-1">
                {stats.outbound_365d} out / {stats.inbound_365d} in
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-stone-500 dark:text-stone-400">Since</span>
          <span className="text-xs font-medium text-stone-900 dark:text-stone-100">
            {format(
              new Date(stats.first_interaction_at || contact.created_at),
              "MMM yyyy"
            )}
          </span>
        </div>
      </div>
    </div>
  );
}
