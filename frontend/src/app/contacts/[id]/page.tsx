"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ChevronDown, Sparkles, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useMergeContacts } from "@/hooks/use-contacts";
import { useContactDetailController } from "./_hooks/use-contact-detail-controller";
import { HeaderCard } from "./_components/header-card";
import { MessageComposerCard } from "./_components/message-composer-card";
import { ChatTimeline } from "./_components/chat-timeline";
import { RelationshipHealth } from "./_components/relationship-health";
import { DetailsPanel } from "./_components/details-panel";
import { CommonGroupsCard } from "./_components/common-groups-card";
import { RelatedContactsCard } from "./_components/related-contacts-card";
import { DuplicatesCard } from "./_components/duplicates-card";
import { AddNoteInput } from "./_components/add-note-input";

export default function ContactDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const ctrl = useContactDetailController(id);
  const mergeContacts = useMergeContacts();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  /* ── Loading state ── */
  if (ctrl.isLoading) {
    return (
      <div className="min-h-screen bg-stone-50 dark:bg-stone-950">
        <main className="max-w-6xl mx-auto px-4 py-8">
          <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-6 mb-6 shimmer">
            <div className="flex items-start gap-6">
              <div className="w-20 h-20 rounded-full bg-stone-200 dark:bg-stone-800" />
              <div className="flex-1 space-y-3">
                <div className="h-6 w-48 bg-stone-200 dark:bg-stone-800 rounded" />
                <div className="h-4 w-72 bg-stone-100 dark:bg-stone-800 rounded" />
                <div className="h-4 w-32 bg-stone-100 dark:bg-stone-800 rounded" />
              </div>
            </div>
          </div>
        </main>
      </div>
    );
  }

  /* ── Not found / error state ── */
  if (ctrl.isError || !ctrl.contact) {
    return (
      <div className="min-h-screen bg-stone-50 dark:bg-stone-950 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-500 mb-4">Contact not found.</p>
          <Link href="/contacts" className="text-teal-600 dark:text-teal-400 hover:underline">
            Back to contacts
          </Link>
        </div>
      </div>
    );
  }

  const contact = ctrl.contact;
  const displayName =
    contact.full_name ??
    [contact.given_name, contact.family_name].filter(Boolean).join(" ") ??
    "Unnamed Contact";

  /* ── Page-level helpers ── */

  const saveField = async (field: string, value: string | string[]) => {
    const input: Record<string, string | string[]> = { [field]: value };
    if (field === "given_name" || field === "family_name") {
      const given =
        field === "given_name" ? (value as string) : (contact.given_name ?? "");
      const family =
        field === "family_name" ? (value as string) : (contact.family_name ?? "");
      input.full_name = [given, family].filter(Boolean).join(" ") || "";
    }
    if (field === "telegram_username" || field === "twitter_handle") {
      try {
        await ctrl.updateContact.mutateAsync({ id, input });
      } catch (err: unknown) {
        const detail = (err as any)?.detail;
        if (detail?.conflicting_contact) {
          const c = detail.conflicting_contact;
          const platformLabel = field === "telegram_username" ? "Telegram username" : "Twitter handle";
          ctrl.setToast({
            type: "error",
            text: `${platformLabel} already used by ${c.full_name || "another contact"}`,
            action: {
              label: "Merge",
              onClick: () => {
                ctrl.setToast(null);
                mergeContacts.mutate(
                  { contactId: id, otherId: c.id },
                  {
                    onSuccess: (result: any) => {
                      const mergedId = result?.data?.id;
                      if (mergedId && mergedId !== id) {
                        router.push(`/contacts/${mergedId}`);
                      } else {
                        router.refresh();
                      }
                    },
                    onError: () => {
                      ctrl.setToast({ type: "error", text: "Merge failed. Try again." });
                    },
                  },
                );
              },
            },
          });
        }
        // Don't re-throw — toast shows the error
      }
      return;
    }
    ctrl.updateContact.mutate({ id, input });
  };

  const handleLinkOrg = (orgId: string, orgName: string) => {
    ctrl.updateContact.mutate({ id, input: { company: orgName, organization_id: orgId } });
  };

  const handleArchive = () => {
    if (contact.priority_level === "archived") {
      ctrl.updateContact.mutate({ id, input: { priority_level: "medium" } });
    } else {
      ctrl.updateContact.mutate(
        { id, input: { priority_level: "archived" } },
        {
          onSuccess: () => {
            ctrl.queryClient.invalidateQueries({ queryKey: ["suggestions"] });
            ctrl.queryClient.invalidateQueries({ queryKey: ["contacts"] });
            router.back();
          },
        },
      );
    }
  };

  return (
    <div className="min-h-screen bg-stone-50 dark:bg-stone-950">
      <main className="max-w-6xl mx-auto px-4 py-8">

        {/* Toast */}
        {ctrl.toast && (
          <div
            className={cn(
              "mb-4 px-4 py-3 rounded-lg text-sm flex items-center gap-2",
              ctrl.toast.type === "success"
                ? "bg-teal-50 dark:bg-teal-950 border border-teal-200 dark:border-teal-800 text-teal-700 dark:text-teal-400"
                : "bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400"
            )}
          >
            {ctrl.toast.type === "success" ? (
              <Sparkles className="w-4 h-4 flex-shrink-0" />
            ) : (
              <X className="w-4 h-4 flex-shrink-0" />
            )}
            {ctrl.toast.text}
            {ctrl.toast.action && (
              <button
                onClick={ctrl.toast.action.onClick}
                className="ml-2 px-2.5 py-1 text-xs font-semibold rounded-md bg-white/80 dark:bg-stone-800/80 border border-current/20 hover:bg-white dark:hover:bg-stone-700 transition-colors"
              >
                {ctrl.toast.action.label}
              </button>
            )}
            <button
              onClick={() => ctrl.setToast(null)}
              className="ml-auto p-0.5 hover:opacity-70"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Header — relative z-10 so kebab dropdown overlaps cards below */}
        <div className="animate-in stagger-1 relative z-10">
        <HeaderCard
          contact={contact}
          allTags={ctrl.allTags}
          isRefreshing={ctrl.isRefreshing}
          isEnriching={ctrl.isEnriching}
          isAutoTagging={ctrl.isAutoTagging}
          onSaveField={saveField}
          onUpdateContact={(input) => ctrl.updateContact.mutate({ id, input })}
          onRefreshDetails={ctrl.handleRefreshDetails}
          onEnrich={ctrl.handleEnrich}
          onAutoTag={ctrl.handleAutoTag}
          onShowDeleteConfirm={() => setShowDeleteConfirm(true)}
          onArchive={handleArchive}
          onPromote={ctrl.handlePromote}
          isPromoting={ctrl.isPromoting}
        />
        </div>

        {/* Delete confirmation modal */}
        {showDeleteConfirm && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center"
            style={{ background: "rgba(28,25,23,0.4)", backdropFilter: "blur(2px)" }}
          >
            <div className="bg-white dark:bg-stone-900 rounded-2xl shadow-2xl p-6 max-w-sm w-full mx-4">
              <h3 className="text-lg font-bold text-stone-900 dark:text-stone-100 mb-2">Delete contact?</h3>
              <p className="text-sm text-stone-600 dark:text-stone-300 mb-5">
                This will permanently delete <strong>{displayName}</strong> and all
                associated interactions.
              </p>
              <div className="flex gap-3 justify-end">
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  className="px-4 py-2 text-sm rounded-lg border border-stone-200 dark:border-stone-700 text-stone-700 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={ctrl.handleDelete}
                  disabled={ctrl.deleteContact.isPending}
                  className="px-4 py-2 text-sm rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
                >
                  {ctrl.deleteContact.isPending ? "Deleting..." : "Delete"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Two-column grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* Main column (2/3) — DOM order 2, visual order 2 on desktop */}
          <div className="animate-in stagger-2 lg:col-span-2 lg:order-2 space-y-4">
            <MessageComposerCard contact={contact} contactId={id} />
            <AddNoteInput onSave={(content) => ctrl.addNoteMutation.mutate(content)} />
            <ChatTimeline
              interactions={ctrl.interactions}
              contactId={id}
              contactName={contact.full_name || contact.given_name || "Contact"}
              onAddNote={(content) => ctrl.addNoteMutation.mutate(content)}
            />
          </div>

          {/* Sidebar (1/3) — DOM order 1, visual order 1 on desktop */}
          <div className="animate-in stagger-3 lg:col-span-1 lg:order-1 space-y-4">
            {/* Mobile toggle — hidden on lg+ */}
            <button
              onClick={() => setSidebarOpen((v) => !v)}
              className="lg:hidden w-full flex items-center justify-between px-4 py-3 bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 text-sm font-medium text-stone-700 dark:text-stone-300"
            >
              Contact Details
              <ChevronDown
                className={cn("w-4 h-4 transition-transform", sidebarOpen && "rotate-180")}
              />
            </button>

            {/* Sidebar content — collapsed on mobile by default */}
            <div className={cn("space-y-4", !sidebarOpen && "hidden lg:block")}>
              {/* Contact Details */}
              <DetailsPanel
                contact={contact}
                onSaveField={saveField}
                onLinkOrg={handleLinkOrg}
                onExtractBio={ctrl.handleExtractBio}
                isExtracting={ctrl.isExtracting}
              />

              {/* Relationship Health */}
              {ctrl.activityLoading ? (
                <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5 shimmer">
                  <div className="h-4 w-40 bg-stone-200 dark:bg-stone-800 rounded mb-4" />
                  <div className="space-y-3">
                    {[1, 2, 3, 4].map((i) => (
                      <div key={i} className="h-1.5 bg-stone-100 dark:bg-stone-800 rounded-full" />
                    ))}
                  </div>
                </div>
              ) : ctrl.activityData ? (
                <RelationshipHealth activityData={ctrl.activityData} contact={contact} />
              ) : null}

              {/* Common Telegram Groups */}
              <CommonGroupsCard
                contactId={id}
                hasTelegram={Boolean(contact.telegram_username)}
              />

              {/* Related Contacts */}
              <RelatedContactsCard contactId={id} />

              {/* Possible Duplicates */}
              <DuplicatesCard contactId={id} />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
