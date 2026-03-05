"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { Bell, TrendingUp, Clock, Users, Sparkles, GitMerge, Mail, MessageCircle, Twitter } from "lucide-react";
import { ScoreBadge } from "@/components/score-badge";
import { formatDistanceToNow } from "date-fns";
import { useDashboardStats } from "@/hooks/use-dashboard";

type Channel = "email" | "telegram" | "twitter";

const channelIcons: Record<Channel, ReactNode> = {
  email: <Mail className="w-3 h-3" />,
  telegram: <MessageCircle className="w-3 h-3" />,
  twitter: <Twitter className="w-3 h-3" />,
};

export default function DashboardPage() {
  const { data, isLoading } = useDashboardStats();

  const { suggestions, recentContacts, totalContacts, relationshipHealth } = data;

  const topSuggestions = suggestions.filter((s) => s.status === "pending").slice(0, 3);

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto px-4 py-8">
        {/* Page header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">Your networking overview</p>
        </div>

        {/* Top stats */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
          <div className="bg-white rounded-lg border border-gray-200 p-4 flex items-center gap-3">
            <div className="p-2 rounded-md bg-blue-50">
              <Users className="w-5 h-5 text-blue-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900">
                {isLoading ? (
                  <span className="inline-block w-8 h-6 bg-gray-100 rounded animate-pulse" />
                ) : (
                  totalContacts
                )}
              </p>
              <p className="text-xs text-gray-500">Total Contacts</p>
            </div>
          </div>

          <div className="bg-white rounded-lg border border-gray-200 p-4 flex items-center gap-3">
            <div className="p-2 rounded-md bg-yellow-50">
              <Bell className="w-5 h-5 text-yellow-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900">
                {isLoading ? (
                  <span className="inline-block w-8 h-6 bg-gray-100 rounded animate-pulse" />
                ) : (
                  suggestions.filter((s) => s.status === "pending").length
                )}
              </p>
              <p className="text-xs text-gray-500">Pending Follow-ups</p>
            </div>
          </div>

          <div className="bg-white rounded-lg border border-gray-200 p-4 flex items-center gap-3">
            <div className="p-2 rounded-md bg-green-50">
              <TrendingUp className="w-5 h-5 text-green-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900">
                {isLoading ? (
                  <span className="inline-block w-8 h-6 bg-gray-100 rounded animate-pulse" />
                ) : (
                  relationshipHealth.strong
                )}
              </p>
              <p className="text-xs text-gray-500">Strong Relationships</p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Reach out this week */}
          <div className="bg-white rounded-lg border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-gray-900 flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-indigo-500" />
                Reach out this week
              </h2>
              <Link
                href="/suggestions"
                className="text-xs text-blue-600 hover:underline"
              >
                View all
              </Link>
            </div>
            {isLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((n) => (
                  <div
                    key={n}
                    className="h-14 rounded-md bg-gray-100 animate-pulse"
                  />
                ))}
              </div>
            ) : topSuggestions.length === 0 ? (
              <p className="text-sm text-gray-400 py-4 text-center">
                No follow-up suggestions yet.{" "}
                <Link href="/suggestions" className="text-indigo-600 hover:underline">
                  Generate suggestions
                </Link>
              </p>
            ) : (
              <ul className="space-y-2">
                {topSuggestions.map((s) => (
                  <li
                    key={s.id}
                    className="flex items-start gap-3 p-3 rounded-md bg-indigo-50 border border-indigo-100"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-gray-800 truncate">
                        {s.contact_name ?? "Contact"}
                      </p>
                      {s.trigger_reason && (
                        <p className="text-xs text-gray-500 truncate">
                          {s.trigger_reason}
                        </p>
                      )}
                    </div>
                    <span className="flex-shrink-0 text-gray-400">
                      {channelIcons[s.suggested_channel]}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Recently contacted */}
          <div className="bg-white rounded-lg border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-gray-900 flex items-center gap-2">
                <Clock className="w-4 h-4 text-blue-500" />
                Recently contacted
              </h2>
              <Link
                href="/contacts"
                className="text-xs text-blue-600 hover:underline"
              >
                View all
              </Link>
            </div>
            {isLoading ? (
              <div className="space-y-2">
                {[1, 2, 3, 4, 5].map((n) => (
                  <div
                    key={n}
                    className="h-10 rounded-md bg-gray-100 animate-pulse"
                  />
                ))}
              </div>
            ) : recentContacts.length === 0 ? (
              <p className="text-sm text-gray-400 py-4 text-center">
                No contacts yet.{" "}
                <Link href="/contacts" className="text-blue-600 hover:underline">
                  Add your first contact
                </Link>
              </p>
            ) : (
              <ul className="space-y-1">
                {recentContacts.map((contact) => {
                  const name =
                    contact.full_name ??
                    [contact.given_name, contact.family_name]
                      .filter(Boolean)
                      .join(" ") ||
                    "Unnamed";
                  return (
                    <li key={contact.id}>
                      <Link
                        href={`/contacts/${contact.id}`}
                        className="flex items-center justify-between p-2 rounded-md hover:bg-gray-50 transition-colors"
                      >
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-gray-800 truncate">
                            {name}
                          </p>
                          {contact.last_interaction_at && (
                            <p className="text-xs text-gray-400">
                              {formatDistanceToNow(
                                new Date(contact.last_interaction_at),
                                { addSuffix: true }
                              )}
                            </p>
                          )}
                        </div>
                        <ScoreBadge
                          score={contact.relationship_score}
                          className="flex-shrink-0 text-xs"
                        />
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* Relationship health */}
          <div className="bg-white rounded-lg border border-gray-200 p-5">
            <h2 className="font-semibold text-gray-900 flex items-center gap-2 mb-4">
              <TrendingUp className="w-4 h-4 text-green-500" />
              Relationship health
            </h2>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="p-3 rounded-lg bg-green-50 border border-green-100">
                <p className="text-3xl font-bold text-green-700">
                  {isLoading ? (
                    <span className="inline-block w-8 h-8 bg-green-100 rounded animate-pulse" />
                  ) : (
                    relationshipHealth.strong
                  )}
                </p>
                <p className="text-xs text-green-600 mt-1">Active (8+)</p>
              </div>
              <div className="p-3 rounded-lg bg-yellow-50 border border-yellow-100">
                <p className="text-3xl font-bold text-yellow-700">
                  {isLoading ? (
                    <span className="inline-block w-8 h-8 bg-yellow-100 rounded animate-pulse" />
                  ) : (
                    relationshipHealth.active
                  )}
                </p>
                <p className="text-xs text-yellow-600 mt-1">Warm (4-7)</p>
              </div>
              <div className="p-3 rounded-lg bg-red-50 border border-red-100">
                <p className="text-3xl font-bold text-red-700">
                  {isLoading ? (
                    <span className="inline-block w-8 h-8 bg-red-100 rounded animate-pulse" />
                  ) : (
                    relationshipHealth.dormant
                  )}
                </p>
                <p className="text-xs text-red-600 mt-1">Cold (0-3)</p>
              </div>
            </div>
          </div>

          {/* Identity resolution quick link */}
          <div className="bg-white rounded-lg border border-gray-200 p-5">
            <h2 className="font-semibold text-gray-900 flex items-center gap-2 mb-4">
              <GitMerge className="w-4 h-4 text-purple-500" />
              Recent activity
            </h2>
            <div className="text-sm text-gray-500 space-y-3">
              <p>
                Keep your network clean by resolving duplicate contacts and
                reviewing AI-suggested follow-ups.
              </p>
              <div className="flex gap-2">
                <Link
                  href="/identity"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-purple-200 text-purple-700 bg-purple-50 hover:bg-purple-100 transition-colors"
                >
                  <GitMerge className="w-3.5 h-3.5" />
                  Identity resolution
                </Link>
                <Link
                  href="/suggestions"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-indigo-200 text-indigo-700 bg-indigo-50 hover:bg-indigo-100 transition-colors"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  Suggestions digest
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
