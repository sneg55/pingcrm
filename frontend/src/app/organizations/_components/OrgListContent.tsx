"use client";

import { OrgTableHeader } from "./OrgTableHeader";
import { OrgTableRow } from "./OrgTableRow";

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

type SortKey = "name" | "contacts" | "score" | "interactions" | "activity";

interface OrgListContentProps {
  isLoading: boolean;
  isError: boolean;
  organizations: Organization[];
  sortedOrganizations: Organization[];
  sortKey: SortKey;
  onSortChange: (key: SortKey) => void;
  selectedOrgIds: Set<string>;
  allSelected: boolean;
  indeterminate: boolean;
  onToggleAll: () => void;
  onToggleOrg: (orgId: string) => void;
  onDeleteOrg: (org: Organization) => void;
}

export function OrgListContent({
  isLoading,
  isError,
  organizations,
  sortedOrganizations,
  sortKey,
  onSortChange,
  selectedOrgIds,
  allSelected,
  indeterminate,
  onToggleAll,
  onToggleOrg,
  onDeleteOrg,
}: OrgListContentProps) {
  if (isLoading) {
    return <div className="text-center py-12 text-gray-400 dark:text-gray-500">Loading organizations...</div>;
  }
  if (isError) {
    return <div className="text-center py-12 text-red-500">Failed to load organizations.</div>;
  }
  if (organizations.length === 0) {
    return <div className="text-center py-12 text-gray-400 dark:text-gray-500">No organizations found.</div>;
  }
  return (
    <div className="animate-in stagger-2 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      <table className="w-full">
        <OrgTableHeader
          sortKey={sortKey}
          onSortChange={onSortChange}
          allSelected={allSelected}
          indeterminate={indeterminate}
          onToggleAll={onToggleAll}
        />
        <tbody className="divide-y divide-gray-50 dark:divide-gray-700">
          {sortedOrganizations.map((org) => (
            <OrgTableRow
              key={org.id}
              org={org}
              isSelected={selectedOrgIds.has(org.id)}
              onToggle={onToggleOrg}
              onDelete={onDeleteOrg}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}
