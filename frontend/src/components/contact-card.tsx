import { formatDistanceToNow } from "date-fns";
import Link from "next/link";
import type { Contact } from "@/hooks/use-contacts";
import { ScoreBadge } from "./score-badge";
import { cn } from "@/lib/utils";

interface ContactCardProps {
  contact: Contact;
  className?: string;
}

export function ContactCard({ contact, className }: ContactCardProps) {
  const displayName =
    contact.full_name ??
    [contact.given_name, contact.family_name].filter(Boolean).join(" ") ??
    "Unnamed Contact";

  return (
    <Link
      href={`/contacts/${contact.id}`}
      className={cn(
        "block p-4 rounded-lg border border-gray-200 bg-white hover:border-blue-300 hover:shadow-sm transition-all",
        className
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="font-semibold text-gray-900 truncate">{displayName}</h3>
          {(contact.title ?? contact.company) && (
            <p className="text-sm text-gray-500 truncate mt-0.5">
              {[contact.title, contact.company].filter(Boolean).join(" at ")}
            </p>
          )}
        </div>
        <ScoreBadge score={contact.relationship_score} className="flex-shrink-0" />
      </div>

      {contact.last_interaction_at && (
        <p className="text-xs text-gray-400 mt-2">
          Last contact{" "}
          {formatDistanceToNow(new Date(contact.last_interaction_at), {
            addSuffix: true,
          })}
        </p>
      )}

      {contact.tags && contact.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {contact.tags.map((tag) => (
            <span
              key={tag}
              className="inline-block px-2 py-0.5 rounded-full text-xs bg-blue-50 text-blue-700 border border-blue-100"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </Link>
  );
}
