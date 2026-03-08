"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { Bell, TrendingUp, Clock, Users, Sparkles, GitMerge, Mail, MessageCircle, Twitter, UserPlus, Cake } from "lucide-react";
import { ScoreBadge } from "@/components/score-badge";
import { ContactAvatar } from "@/components/contact-avatar";
import { formatDistanceToNow } from "date-fns";
import { useDashboardStats, type BirthdayContact } from "@/hooks/use-dashboard";

type Channel = "email" | "telegram" | "twitter";

const channelIcons: Record<Channel, ReactNode> = {
  email: <Mail className="w-3 h-3" />,
  telegram: <MessageCircle className="w-3 h-3" />,
  twitter: <Twitter className="w-3 h-3" />,
};

function RelationshipBar({ strong, active, dormant }: { strong: number; active: number; dormant: number }) {
  const total = strong + active + dormant;
  if (total === 0) return null;
  const strongPct = (strong / total) * 100;
  const activePct = (active / total) * 100;
  const dormantPct = (dormant / total) * 100;

  return (
    <div className="space-y-3">
      <div className="h-7 rounded-lg overflow-hidden flex bg-stone-100 text-xs font-medium">
        {strongPct > 0 && (
          <div
            className="bg-emerald-500 text-white flex items-center justify-center transition-all duration-500"
            style={{ width: `${strongPct}%` }}
            title={`Strong: ${strong}`}
          >
            {strongPct > 8 && strong}
          </div>
        )}
        {activePct > 0 && (
          <div
            className="bg-amber-400 text-amber-900 flex items-center justify-center transition-all duration-500"
            style={{ width: `${activePct}%` }}
            title={`Warm: ${active}`}
          >
            {activePct > 8 && active}
          </div>
        )}
        {dormantPct > 0 && (
          <div
            className="bg-red-400 text-white flex items-center justify-center transition-all duration-500"
            style={{ width: `${dormantPct}%` }}
            title={`Cold: ${dormant}`}
          >
            {dormantPct > 8 && dormant}
          </div>
        )}
      </div>
      <div className="flex justify-between text-xs">
        <Link href="/contacts?score=strong" className="flex items-center gap-1.5 text-emerald-700 hover:underline">
          <span className="w-2 h-2 rounded-full bg-emerald-500" />
          Strong <span className="font-mono-data">{strong}</span>
        </Link>
        <Link href="/contacts?score=active" className="flex items-center gap-1.5 text-amber-700 hover:underline">
          <span className="w-2 h-2 rounded-full bg-amber-400" />
          Warm <span className="font-mono-data">{active}</span>
        </Link>
        <Link href="/contacts?score=dormant" className="flex items-center gap-1.5 text-red-600 hover:underline">
          <span className="w-2 h-2 rounded-full bg-red-400" />
          Cold <span className="font-mono-data">{dormant}</span>
        </Link>
      </div>
    </div>
  );
}

function humanizeSource(source: string): string {
  const map: Record<string, string> = {
    google_calendar: "Calendar",
    google_contacts: "Google",
    telegram: "Telegram",
    twitter: "Twitter",
    csv_import: "CSV Import",
    linkedin_import: "LinkedIn",
    manual: "Manual",
  };
  return map[source] ?? source;
}

export default function DashboardPage() {
  const { data, isLoading } = useDashboardStats();

  const { suggestions, recentContacts, newContacts, upcomingBirthdays, totalContacts, relationshipHealth } = data;

  const topSuggestions = suggestions.filter((s) => s.status === "pending").slice(0, 3);

  return (
    <div className="min-h-screen bg-stone-50">
      <div className="max-w-6xl mx-auto px-4 py-8">
        {/* Page header */}
        <div className="mb-8">
          <h1 className="text-2xl font-display font-bold text-stone-900">Dashboard</h1>
          <p className="text-sm text-stone-500 mt-1">Your networking overview</p>
        </div>

        {/* Top stats */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
          <div className="bg-white rounded-lg border border-stone-200 p-4 flex items-center gap-3 card-hover animate-fade-in-up">
            <div className="p-2 rounded-md bg-teal-50">
              <Users className="w-5 h-5 text-teal-600" />
            </div>
            <div>
              <p className="text-3xl font-bold text-stone-900 font-mono-data">
                {isLoading ? (
                  <span className="inline-block w-10 h-8 bg-stone-100 rounded animate-pulse" />
                ) : (
                  totalContacts
                )}
              </p>
              <p className="text-xs text-stone-500">Total Contacts</p>
            </div>
          </div>

          <div className="bg-white rounded-lg border border-stone-200 p-4 flex items-center gap-3 card-hover animate-fade-in-up" style={{ animationDelay: "60ms" }}>
            <div className="p-2 rounded-md bg-amber-50">
              <Bell className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <p className="text-3xl font-bold text-stone-900 font-mono-data">
                {isLoading ? (
                  <span className="inline-block w-10 h-8 bg-stone-100 rounded animate-pulse" />
                ) : (
                  suggestions.filter((s) => s.status === "pending").length
                )}
              </p>
              <p className="text-xs text-stone-500">Pending Follow-ups</p>
            </div>
          </div>

          <div className="bg-white rounded-lg border border-stone-200 p-4 flex items-center gap-3 card-hover animate-fade-in-up" style={{ animationDelay: "120ms" }}>
            <div className="p-2 rounded-md bg-emerald-50">
              <TrendingUp className="w-5 h-5 text-emerald-600" />
            </div>
            <div>
              <p className="text-3xl font-bold text-stone-900 font-mono-data">
                {isLoading ? (
                  <span className="inline-block w-10 h-8 bg-stone-100 rounded animate-pulse" />
                ) : (
                  relationshipHealth.strong
                )}
              </p>
              <p className="text-xs text-stone-500">Strong Relationships</p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Reach out this week */}
          <div className="bg-white rounded-lg border border-stone-200 p-5 card-hover">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display font-semibold text-stone-900 flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-teal-500" />
                Reach out this week
              </h2>
              <Link
                href="/suggestions"
                className="text-xs text-teal-600 hover:underline"
              >
                View all
              </Link>
            </div>
            {isLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((n) => (
                  <div
                    key={n}
                    className="h-14 rounded-md bg-stone-100 animate-pulse"
                  />
                ))}
              </div>
            ) : topSuggestions.length === 0 ? (
              <div className="text-center py-6">
                <Sparkles className="w-8 h-8 text-stone-200 mx-auto mb-2 animate-float" />
                <p className="text-sm text-stone-400">
                  No follow-up suggestions yet.{" "}
                  <Link href="/suggestions" className="text-teal-600 hover:underline">
                    Generate suggestions
                  </Link>
                </p>
              </div>
            ) : (
              <ul className="space-y-1">
                {topSuggestions.map((s) => {
                  const name = s.contact?.full_name ?? ([s.contact?.given_name, s.contact?.family_name].filter(Boolean).join(" ") || "Contact");
                  return (
                    <li key={s.id}>
                      <Link
                        href={`/contacts/${s.contact_id}`}
                        className="flex items-center gap-3 p-2 rounded-md hover:bg-stone-50 transition-colors"
                      >
                        <ContactAvatar
                          avatarUrl={s.contact?.avatar_url}
                          name={name}
                          size="sm"
                        />
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-stone-800 truncate">
                            {name}
                          </p>
                          <p className="text-xs text-stone-400 truncate">
                            {s.trigger_type === "birthday" ? "🎂 Birthday coming up" : s.trigger_type === "time_based" ? "No interaction in 90+ days" : s.trigger_type === "event_based" ? "New event detected" : "Scheduled follow-up"}
                          </p>
                        </div>
                        <span className="flex-shrink-0 text-stone-400">
                          {channelIcons[s.suggested_channel]}
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* Recently contacted */}
          <div className="bg-white rounded-lg border border-stone-200 p-5 card-hover">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display font-semibold text-stone-900 flex items-center gap-2">
                <Clock className="w-4 h-4 text-teal-500" />
                Recently contacted
              </h2>
              <Link
                href="/contacts"
                className="text-xs text-teal-600 hover:underline"
              >
                View all
              </Link>
            </div>
            {isLoading ? (
              <div className="space-y-2">
                {[1, 2, 3, 4, 5].map((n) => (
                  <div
                    key={n}
                    className="h-10 rounded-md bg-stone-100 animate-pulse"
                  />
                ))}
              </div>
            ) : recentContacts.length === 0 ? (
              <div className="text-center py-6">
                <Users className="w-8 h-8 text-stone-200 mx-auto mb-2 animate-float" />
                <p className="text-sm text-stone-400">
                  No contacts yet.{" "}
                  <Link href="/contacts" className="text-teal-600 hover:underline">
                    Add your first contact
                  </Link>
                </p>
              </div>
            ) : (
              <ul className="space-y-1">
                {recentContacts.map((contact) => {
                  const name =
                    contact.full_name ??
                    ([contact.given_name, contact.family_name]
                      .filter(Boolean)
                      .join(" ") ||
                    "Unnamed");
                  return (
                    <li key={contact.id}>
                      <Link
                        href={`/contacts/${contact.id}`}
                        className="flex items-center gap-3 p-2 rounded-md hover:bg-stone-50 transition-colors"
                      >
                        <ContactAvatar
                          avatarUrl={contact.avatar_url}
                          name={name}
                          size="sm"
                          score={contact.relationship_score}
                        />
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-stone-800 truncate">
                            {name}
                          </p>
                          {contact.last_interaction_at && (
                            <p className="text-xs text-stone-400">
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

          {/* Relationship health — stacked bar */}
          <div className="bg-white rounded-lg border border-stone-200 p-5 card-hover">
            <h2 className="font-display font-semibold text-stone-900 flex items-center gap-2 mb-4">
              <TrendingUp className="w-4 h-4 text-emerald-500" />
              Relationship health
            </h2>
            {isLoading ? (
              <div className="h-20 bg-stone-100 rounded-lg animate-pulse" />
            ) : (
              <RelationshipBar
                strong={relationshipHealth.strong}
                active={relationshipHealth.active}
                dormant={relationshipHealth.dormant}
              />
            )}
          </div>

          {/* Quick links */}
          <div className="bg-white rounded-lg border border-stone-200 p-5 card-hover">
            <h2 className="font-display font-semibold text-stone-900 flex items-center gap-2 mb-4">
              <GitMerge className="w-4 h-4 text-violet-500" />
              Quick actions
            </h2>
            <div className="text-sm text-stone-500 space-y-3">
              <p>
                Keep your network clean by resolving duplicate contacts and
                reviewing AI-suggested follow-ups.
              </p>
              <div className="flex gap-2">
                <Link
                  href="/identity"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-violet-200 text-violet-700 bg-violet-50 hover:bg-violet-100 transition-colors btn-press"
                >
                  <GitMerge className="w-3.5 h-3.5" />
                  Identity resolution
                </Link>
                <Link
                  href="/suggestions"
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-teal-200 text-teal-700 bg-teal-50 hover:bg-teal-100 transition-colors btn-press"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  Suggestions digest
                </Link>
              </div>
            </div>
          </div>
        </div>

        {/* New contacts + Birthdays row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
          {/* New contacts */}
          <div className="bg-white rounded-lg border border-stone-200 p-5 card-hover">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display font-semibold text-stone-900 flex items-center gap-2">
                <UserPlus className="w-4 h-4 text-teal-500" />
                New contacts with recent interactions
              </h2>
              <Link
                href="/contacts?sort=created&interaction_days=30"
                className="text-xs text-teal-600 hover:underline"
              >
                View all
              </Link>
            </div>
            {isLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((n) => (
                  <div
                    key={n}
                    className="h-12 rounded-md bg-stone-100 animate-pulse"
                  />
                ))}
              </div>
            ) : newContacts.length === 0 ? (
              <div className="text-center py-6">
                <UserPlus className="w-8 h-8 text-stone-200 mx-auto mb-2 animate-float" />
                <p className="text-sm text-stone-400">
                  No contacts yet.{" "}
                  <Link href="/contacts" className="text-teal-600 hover:underline">
                    Add your first contact
                  </Link>
                </p>
              </div>
            ) : (
              <ul className="space-y-1">
                {newContacts.map((contact) => {
                  const name =
                    contact.full_name ??
                    ([contact.given_name, contact.family_name]
                      .filter(Boolean)
                      .join(" ") ||
                    "Unnamed");
                  return (
                    <li key={contact.id}>
                      <Link
                        href={`/contacts/${contact.id}`}
                        className="flex items-center gap-3 p-2 rounded-md hover:bg-stone-50 transition-colors"
                      >
                        <ContactAvatar
                          avatarUrl={contact.avatar_url}
                          name={name}
                          size="sm"
                        />
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-stone-800 truncate">
                            {name}
                          </p>
                          <p className="text-xs text-stone-400 truncate">
                            {[contact.title, contact.company].filter(Boolean).join(" at ") || (contact.source ? humanizeSource(contact.source) : "") || ""}
                            {contact.created_at && (
                              <span>
                                {(contact.title || contact.company || contact.source) ? " \u00b7 " : ""}
                                Added {formatDistanceToNow(new Date(contact.created_at), { addSuffix: true })}
                              </span>
                            )}
                          </p>
                        </div>
                        {contact.source && (
                          <span className="flex-shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded bg-stone-100 text-stone-500">
                            {humanizeSource(contact.source)}
                          </span>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* Birthdays this week */}
          <div className="bg-white rounded-lg border border-stone-200 p-5 card-hover">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display font-semibold text-stone-900 flex items-center gap-2">
                <Cake className="w-4 h-4 text-rose-500" />
                Birthdays this week
              </h2>
              <Link
                href="/contacts?has_birthday=true&sort=birthday"
                className="text-xs text-teal-600 hover:underline"
              >
                View all
              </Link>
            </div>
            {isLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((n) => (
                  <div
                    key={n}
                    className="h-12 rounded-md bg-stone-100 animate-pulse"
                  />
                ))}
              </div>
            ) : upcomingBirthdays.length === 0 ? (
              <div className="text-center py-6">
                <Cake className="w-8 h-8 text-stone-200 mx-auto mb-2 animate-float" />
                <p className="text-sm text-stone-400">
                  No birthdays this week
                </p>
              </div>
            ) : (
              <ul className="space-y-1">
                {upcomingBirthdays.map((contact: BirthdayContact) => {
                  const name =
                    contact.full_name ??
                    ([contact.given_name, contact.family_name]
                      .filter(Boolean)
                      .join(" ") ||
                    "Unnamed");
                  const days = contact.days_until_birthday;
                  const label =
                    days === 0
                      ? "Today!"
                      : days === 1
                        ? "Tomorrow"
                        : `In ${days} days`;
                  return (
                    <li key={contact.id}>
                      <Link
                        href={`/contacts/${contact.id}`}
                        className="flex items-center gap-3 p-2 rounded-md hover:bg-stone-50 transition-colors"
                      >
                        <ContactAvatar
                          avatarUrl={contact.avatar_url}
                          name={name}
                          size="sm"
                        />
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-stone-800 truncate">
                            {name}
                          </p>
                          <p className="text-xs text-stone-400">
                            {contact.birthday}
                          </p>
                        </div>
                        <span className={`flex-shrink-0 text-xs font-medium px-2 py-0.5 rounded-full ${
                          days === 0
                            ? "bg-rose-100 text-rose-700"
                            : days === 1
                              ? "bg-amber-100 text-amber-700"
                              : "bg-stone-100 text-stone-600"
                        }`}>
                          {label}
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
