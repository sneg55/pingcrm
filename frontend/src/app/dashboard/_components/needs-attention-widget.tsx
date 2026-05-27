"use client";

import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import { ContactAvatar } from "@/components/contact-avatar";
import { type OverdueContact } from "@/hooks/use-dashboard";

function OverdueRow({ contact }: { contact: OverdueContact }) {
  const name =
    contact.full_name ??
    ([contact.given_name, contact.family_name].filter(Boolean).join(" ") || "Unnamed");
  const daysLabel =
    contact.days_overdue <= 0
      ? "due today"
      : `${contact.days_overdue}d overdue`;
  const isUrgent = contact.days_overdue > 5;

  return (
    <Link
      href={`/contacts/${contact.id}`}
      className="card-hover flex items-center gap-3 hover:bg-stone-50 dark:hover:bg-stone-800 rounded-md p-1 -mx-1 transition-colors"
    >
      <ContactAvatar
        avatarUrl={contact.avatar_url}
        name={name}
        size="xs"
      />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-stone-900 dark:text-stone-100 truncate">{name}</p>
        <p className="text-xs text-stone-400 dark:text-stone-500">
          {contact.last_interaction_at
            ? `${formatDistanceToNow(new Date(contact.last_interaction_at))} since last contact`
            : "No interactions"}
        </p>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <span className={`w-1.5 h-1.5 rounded-full ${isUrgent ? "bg-red-400" : "bg-amber-400"}`} />
        <span
          className={`text-[11px] font-mono ${isUrgent ? "text-red-600 dark:text-red-400" : "text-amber-600 dark:text-amber-400"}`}
        >
          {daysLabel}
        </span>
      </div>
    </Link>
  );
}

interface Props {
  isLoading: boolean;
  overdueContacts: OverdueContact[];
}

export function NeedsAttentionWidget({ isLoading, overdueContacts }: Props) {
  return (
    <div className="lg:col-span-2 space-y-6 animate-in stagger-2">
      <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-display font-semibold text-stone-900 dark:text-stone-100">
            Needs Attention
          </h2>
          {overdueContacts.length > 0 && (
            <span className="text-[11px] font-medium text-red-500 dark:text-red-400 bg-red-50 dark:bg-red-950 px-2 py-0.5 rounded-full">
              {overdueContacts.length} contact{overdueContacts.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        <p className="text-xs text-stone-400 dark:text-stone-500 mb-4">
          High-priority contacts going silent
        </p>
        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((n) => (
              <div
                key={n}
                className="h-10 rounded-md bg-stone-100 dark:bg-stone-800 shimmer"
              />
            ))}
          </div>
        ) : overdueContacts.length === 0 ? (
          <p className="text-sm text-stone-400 dark:text-stone-500 text-center py-4">
            All caught up!
          </p>
        ) : (
          <div className="space-y-3">
            {overdueContacts.map((contact) => (
              <OverdueRow key={contact.id} contact={contact} />
            ))}
          </div>
        )}
        {overdueContacts.length > 0 && (
          <Link
            href="/contacts?sort=overdue"
            className="block text-center text-xs font-medium text-teal-600 dark:text-teal-400 hover:text-teal-700 dark:hover:text-teal-300 mt-4 pt-3 border-t border-stone-100 dark:border-stone-800"
          >
            View all &rarr;
          </Link>
        )}
      </div>
    </div>
  );
}
