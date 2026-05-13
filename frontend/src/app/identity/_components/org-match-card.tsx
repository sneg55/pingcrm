"use client";

import { MatchCardShell, type BreakdownRow } from "./match-card-shell";
import { OrgPanel } from "./org-panel";
import type { OrgIdentityMatch, OrgSummary } from "@/hooks/use-org-identity";

const ORG_BREAKDOWN: BreakdownRow[] = [
  { label: "Name", weight: 40 },
  { label: "Domain", weight: 20 },
  { label: "LinkedIn", weight: 20 },
  { label: "Website", weight: 10 },
  { label: "Twitter", weight: 10 },
];

function pickTarget(a: OrgSummary, b: OrgSummary): OrgSummary {
  return a.contact_count >= b.contact_count ? a : b;
}

export function OrgMatchCard({
  match,
  onMerge,
  onReject,
  merging,
  rejecting,
}: {
  match: OrgIdentityMatch;
  onMerge: (targetId: string) => void;
  onReject: () => void;
  merging: boolean;
  rejecting: boolean;
}) {
  const target = pickTarget(match.org_a, match.org_b);

  return (
    <MatchCardShell
      matchScore={match.match_score ?? 0}
      matchMethod={match.match_method}
      breakdownRows={ORG_BREAKDOWN}
      leftPanel={<OrgPanel org={match.org_a} />}
      rightPanel={<OrgPanel org={match.org_b} />}
      mergeButtonLabel={`Merge into ${target.name}`}
      onMerge={() => onMerge(target.id)}
      onReject={onReject}
      merging={merging}
      rejecting={rejecting}
    />
  );
}
