"use client";

import { BarChart3, MessageSquare, Users, ArrowDown, ArrowUpDown } from "lucide-react";

type SortKey = "name" | "contacts" | "score" | "interactions" | "activity";

interface OrgTableHeaderProps {
  sortKey: SortKey;
  onSortChange: (key: SortKey) => void;
  allSelected: boolean;
  indeterminate: boolean;
  onToggleAll: () => void;
}

const COLUMNS: { key: SortKey; label: string; align: string; icon: React.ComponentType<{ className?: string }> | null }[] = [
  { key: "name", label: "Organization", align: "text-left", icon: null },
  { key: "contacts", label: "Contacts", align: "text-center", icon: Users },
  { key: "score", label: "Avg Score", align: "text-center", icon: BarChart3 },
  { key: "interactions", label: "Interactions", align: "text-center", icon: MessageSquare },
  { key: "activity", label: "Last Activity", align: "text-right", icon: null },
];

export function OrgTableHeader({ sortKey, onSortChange, allSelected, indeterminate, onToggleAll }: OrgTableHeaderProps) {
  return (
    <thead>
      <tr className="border-b border-gray-100 dark:border-gray-700 text-left text-xs text-gray-500 dark:text-gray-400">
        <th className="w-10 px-4 py-3">
          <input
            type="checkbox"
            checked={allSelected}
            ref={(el) => {
              if (el) el.indeterminate = indeterminate;
            }}
            onChange={onToggleAll}
            className="w-4 h-4 rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
            aria-label="Select all organizations"
          />
        </th>
        {COLUMNS.map((col) => (
          <th
            key={col.key}
            className={`px-4 py-3 font-medium ${col.align} cursor-pointer select-none hover:text-blue-600 transition-colors group`}
            onClick={() => onSortChange(col.key)}
          >
            <span className="inline-flex items-center gap-1">
              {col.icon ? <col.icon className="w-3.5 h-3.5" /> : col.label}
              {sortKey === col.key ? (
                <ArrowDown className="w-3 h-3" />
              ) : (
                <ArrowUpDown className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
              )}
            </span>
          </th>
        ))}
        <th className="w-10 px-4 py-3" />
      </tr>
    </thead>
  );
}
