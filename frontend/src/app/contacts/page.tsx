"use client";

import { useState } from "react";
import Link from "next/link";
import { Search, Plus, UserCircle } from "lucide-react";
import { useContacts } from "@/hooks/use-contacts";
import { ScoreBadge } from "@/components/score-badge";
import { formatDistanceToNow } from "date-fns";

export default function ContactsPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading, isError } = useContacts({
    search: search || undefined,
    page,
    page_size: 20,
  });

  const contacts = data?.data ?? [];
  const meta = data?.meta;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Contacts</h1>
            {meta && (
              <p className="text-sm text-gray-500 mt-0.5">
                {meta.total} total contacts
              </p>
            )}
          </div>
          <Link
            href="/contacts/new"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add Contact
          </Link>
        </div>

        <div className="relative mb-6">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search by name or company..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="w-full pl-9 pr-4 py-2.5 rounded-lg border border-gray-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
        </div>

        {isLoading && (
          <div className="text-center py-12 text-gray-400">Loading contacts...</div>
        )}

        {isError && (
          <div className="text-center py-12 text-red-500">
            Failed to load contacts. Is the backend running?
          </div>
        )}

        {!isLoading && !isError && contacts.length === 0 && (
          <div className="text-center py-12 text-gray-400">
            No contacts found.
          </div>
        )}

        {contacts.length > 0 && (
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Name</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Company</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Score</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Last Interaction</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {contacts.map((contact) => {
                  const name =
                    contact.full_name ??
                    [contact.given_name, contact.family_name].filter(Boolean).join(" ") ??
                    "Unnamed";
                  return (
                    <tr key={contact.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <Link
                          href={`/contacts/${contact.id}`}
                          className="flex items-center gap-2 text-blue-600 hover:text-blue-800 font-medium"
                        >
                          <UserCircle className="w-5 h-5 text-gray-400" />
                          {name}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-gray-600">
                        {contact.company ?? "-"}
                      </td>
                      <td className="px-4 py-3">
                        <ScoreBadge score={contact.relationship_score} />
                      </td>
                      <td className="px-4 py-3 text-gray-500">
                        {contact.last_interaction_at
                          ? formatDistanceToNow(new Date(contact.last_interaction_at), {
                              addSuffix: true,
                            })
                          : "Never"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {meta && meta.total_pages > 1 && (
          <div className="flex items-center justify-between mt-4">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="px-3 py-1.5 text-sm rounded-md border border-gray-300 disabled:opacity-40 hover:bg-gray-100"
            >
              Previous
            </button>
            <span className="text-sm text-gray-500">
              Page {page} of {meta.total_pages}
            </span>
            <button
              disabled={page >= meta.total_pages}
              onClick={() => setPage((p) => p + 1)}
              className="px-3 py-1.5 text-sm rounded-md border border-gray-300 disabled:opacity-40 hover:bg-gray-100"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
