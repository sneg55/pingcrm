import { Users } from "lucide-react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ContactAvatar } from "@/components/contact-avatar";
import { client } from "@/lib/api-client";

interface RelatedContact {
  id: string;
  full_name: string;
  title: string | null;
  company: string | null;
  avatar_url: string | null;
  relationship_score: number;
  reasons: string[];
}

export function RelatedContactsCard({ contactId }: { contactId: string }) {
  const { data } = useQuery({
    queryKey: ["related-contacts", contactId],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/contacts/{contact_id}/related" as any, {
        params: { path: { contact_id: contactId } },
      });
      return (data as any)?.data ?? [];
    },
    enabled: Boolean(contactId),
  });

  const related: RelatedContact[] = data ?? [];
  if (related.length === 0) return null;

  return (
    <div className="bg-white rounded-xl border border-stone-200 p-5">
      <h3 className="text-sm font-semibold text-stone-900 mb-3 flex items-center gap-2">
        <Users className="w-4 h-4 text-violet-500" />
        Related Contacts
      </h3>
      <div className="space-y-3">
        {related.map((c) => {
          // Build subtitle: "Title @ Company" or just company/title
          const subtitle = c.title && c.company
            ? `${c.title} @ ${c.company}`
            : c.title || c.company || null;

          // Filter out "Same org"/"Same company" from reasons since we show title@company
          const filteredReasons = c.reasons.filter(
            (r) => r !== "Same org" && r !== "Same company"
          );

          return (
            <div key={c.id} className="flex items-start gap-2.5">
              <ContactAvatar
                avatarUrl={c.avatar_url}
                name={c.full_name}
                size="sm"
              />
              <div className="min-w-0 flex-1">
                <Link
                  href={`/contacts/${c.id}`}
                  className="text-xs font-medium text-stone-800 hover:text-teal-600 truncate block"
                >
                  {c.full_name}
                </Link>
                {subtitle && (
                  <p className="text-[10px] text-stone-500 truncate">{subtitle}</p>
                )}
                {filteredReasons.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1">
                    {filteredReasons.map((reason) => (
                      <span
                        key={reason}
                        className="text-[10px] font-medium bg-stone-100 text-stone-600 rounded-full px-2 py-0.5"
                      >
                        {reason}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
