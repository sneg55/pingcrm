"use client";

import Link from "next/link";
import { Building2, Globe, Linkedin, Twitter, Users } from "lucide-react";

import { CompanyFavicon } from "@/components/company-favicon";
import type { OrgSummary } from "@/hooks/use-org-identity";

function safeHref(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  return /^https?:\/\//i.test(url) ? url : `https://${url}`;
}

export function OrgPanel({ org }: { org: OrgSummary }) {
  return (
    <div className="bg-stone-50 dark:bg-stone-800 rounded-lg p-4 border border-stone-100 dark:border-stone-700">
      <div className="flex items-center gap-3 mb-3">
        <CompanyFavicon
          logoUrl={org.logo_url}
          domain={org.domain}
          size="w-10 h-10"
        />
        <div className="min-w-0 flex-1">
          <Link
            href={`/organizations/${org.id}`}
            className="text-sm font-semibold text-stone-900 dark:text-stone-100 hover:text-teal-700 dark:hover:text-teal-400 transition-colors truncate block"
            onClick={(e) => e.stopPropagation()}
          >
            {org.name}
          </Link>
          <p className="text-xs text-stone-400 dark:text-stone-500">
            <Users className="inline w-3 h-3 mr-1" />
            {org.contact_count} contact{org.contact_count !== 1 ? "s" : ""}
          </p>
        </div>
      </div>

      <div className="space-y-1.5 text-xs text-stone-600 dark:text-stone-300">
        {org.domain && (
          <div className="flex items-center gap-2">
            <Building2 className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
            <span className="font-mono truncate">{org.domain}</span>
          </div>
        )}
        {org.website && (
          <div className="flex items-center gap-2 truncate">
            <Globe className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
            <a
              href={safeHref(org.website)}
              target="_blank"
              rel="noopener noreferrer"
              className="text-teal-600 dark:text-teal-400 hover:underline font-mono truncate"
            >
              {org.website}
            </a>
          </div>
        )}
        {org.linkedin_url && (
          <div className="flex items-center gap-2 truncate">
            <Linkedin className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
            <a
              href={safeHref(org.linkedin_url)}
              target="_blank"
              rel="noopener noreferrer"
              className="text-teal-600 dark:text-teal-400 hover:underline font-mono truncate"
            >
              LinkedIn
            </a>
          </div>
        )}
        {org.twitter_handle && (
          <div className="flex items-center gap-2">
            <Twitter className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500 shrink-0" />
            <span className="font-mono">@{org.twitter_handle}</span>
          </div>
        )}
      </div>
    </div>
  );
}
