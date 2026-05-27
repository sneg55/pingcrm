"use client";

import Link from "next/link";
import { Trash2 } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { CompanyFavicon } from "@/components/company-favicon";

type Organization = {
  id: string;
  name: string;
  domain: string | null;
  logo_url: string | null;
  industry: string | null;
  location: string | null;
  website: string | null;
  linkedin_url: string | null;
  twitter_handle: string | null;
  notes: string | null;
  contact_count: number;
  avg_relationship_score: number;
  total_interactions: number;
  last_interaction_at: string | null;
};

interface OrgTableRowProps {
  org: Organization;
  isSelected: boolean;
  onToggle: (orgId: string) => void;
  onDelete: (org: Organization) => void;
}

export function OrgTableRow({ org, isSelected, onToggle, onDelete }: OrgTableRowProps) {
  return (
    <tr
      className={`card-hover hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors ${
        isSelected ? "bg-blue-50/50 dark:bg-blue-950/30" : ""
      }`}
    >
      <td className="px-4 py-3">
        <input
          type="checkbox"
          checked={isSelected}
          onChange={() => onToggle(org.id)}
          className="w-4 h-4 rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
          aria-label={`Select ${org.name}`}
        />
      </td>
      <td className="px-4 py-3">
        <Link href={`/organizations/${org.id}`} className="flex items-center gap-3 group">
          <div className="w-8 h-8 rounded-lg bg-blue-50 dark:bg-blue-950 flex items-center justify-center flex-shrink-0 overflow-hidden">
            <CompanyFavicon logoUrl={org.logo_url} domain={org.domain} size="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <span className="text-sm font-semibold text-gray-900 dark:text-gray-100 group-hover:text-blue-600 transition-colors">
              {org.name}
            </span>
            {org.domain && (
              <span className="ml-2 text-xs text-gray-400 dark:text-gray-500">{org.domain}</span>
            )}
          </div>
        </Link>
      </td>
      <td className="px-4 py-3 text-center text-sm text-gray-600 dark:text-gray-400">
        {org.contact_count}
      </td>
      <td className="px-4 py-3 text-center text-sm text-gray-600 dark:text-gray-400">
        {org.avg_relationship_score || "-"}
      </td>
      <td className="px-4 py-3 text-center text-sm text-gray-600 dark:text-gray-400">
        {org.total_interactions || "-"}
      </td>
      <td className="px-4 py-3 text-right text-xs text-gray-400 dark:text-gray-500">
        {org.last_interaction_at
          ? formatDistanceToNow(new Date(org.last_interaction_at), { addSuffix: true })
          : "Never"}
      </td>
      <td className="px-4 py-3">
        <button
          onClick={() => onDelete(org)}
          className="p-1 rounded text-gray-300 dark:text-gray-600 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950 transition-colors"
          title={`Delete ${org.name}`}
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </td>
    </tr>
  );
}
