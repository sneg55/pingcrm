"use client";

export const dynamic = "force-dynamic";

import { Suspense, useState, useEffect, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { Plug, FileDown, Clock, Tag, User, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSettingsController, type TabId } from "./_hooks/use-settings-controller";
import { useTelegramConnectFlow } from "./_hooks/use-telegram-connect-flow";
import { useWhatsAppConnectFlow } from "./_hooks/use-whatsapp-connect-flow";
import { SuccessModal } from "./_components/shared";
import { IntegrationsTab } from "./_components/integrations-tab";
import { ImportTab } from "./_components/import-tab";
import { FollowUpRulesTab } from "./_components/followup-tab";
import { TagsTab } from "./_components/tags-tab";
import { AccountTab } from "./_components/account-tab";

/* ── Tab metadata (labels + icons for the bar) ── */
const TABS = [
  { id: "integrations", label: "Integrations", icon: Plug },
  { id: "import", label: "Import", icon: FileDown },
  { id: "followup", label: "Follow-up Rules", icon: Clock },
  { id: "tags", label: "Tags", icon: Tag },
  { id: "account", label: "Account", icon: User },
] as const;

/* ── Tab bar ── */
function TabBar({ activeTab, onChange }: { activeTab: TabId; onChange: (tab: TabId) => void }) {
  const [indicatorStyle, setIndicatorStyle] = useState({ left: 0, width: 0 });
  const barRef = useCallback(
    (bar: HTMLDivElement | null) => {
      if (!bar) return;
      const activeBtn = bar.querySelector(`[data-tab="${activeTab}"]`) as HTMLElement | null;
      if (!activeBtn) return;
      const barRect = bar.getBoundingClientRect();
      const btnRect = activeBtn.getBoundingClientRect();
      setIndicatorStyle({ left: btnRect.left - barRect.left, width: btnRect.width });
    },
    [activeTab]
  );

  return (
    <div ref={barRef} className="relative border-b border-stone-200 dark:border-stone-700 mb-8">
      <div className="flex gap-1 overflow-x-auto scrollbar-hide">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            data-tab={tab.id}
            onClick={() => onChange(tab.id)}
            className={cn(
              "relative px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap shrink-0",
              activeTab === tab.id ? "text-teal-700 dark:text-teal-400" : "text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-300"
            )}
          >
            <span className="flex items-center gap-2">
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </span>
          </button>
        ))}
      </div>
      <div
        className="absolute bottom-[-1px] h-[2px] bg-teal-600 rounded-sm transition-all duration-300"
        style={{ left: indicatorStyle.left, width: indicatorStyle.width }}
      />
    </div>
  );
}

/* ── Loading fallback ── */
function Loading() {
  return (
    <div className="min-h-screen bg-stone-50 dark:bg-stone-950 flex items-center justify-center">
      <div className="animate-spin h-8 w-8 border-4 border-teal-500 border-t-transparent rounded-full" />
    </div>
  );
}

/* ── Inner content (requires useSearchParams) ── */
function SettingsContent() {
  const ctrl = useSettingsController();
  const telegramFlow = useTelegramConnectFlow({
    telegramConnect: ctrl.telegramConnect,
    setTelegramConnect: ctrl.setTelegramConnect,
    showTelegramModal: ctrl.showTelegramModal,
    setShowTelegramModal: ctrl.setShowTelegramModal,
    onSuccess: (username) => ctrl.showSuccessModal("Telegram", username),
  });
  const whatsappFlow = useWhatsAppConnectFlow({
    whatsappConnect: ctrl.whatsappConnect,
    setWhatsappConnect: ctrl.setWhatsappConnect,
    onSuccess: ctrl.fetchConnectionStatus,
  });

  if (ctrl.isLoading) {
    return (
      <div className="min-h-screen bg-stone-50 dark:bg-stone-950">
        <div className="max-w-3xl mx-auto px-4 py-8">
          <h1 className="text-2xl font-bold text-stone-900 dark:text-stone-100 mb-1">Settings</h1>
          <p className="text-sm text-stone-500 dark:text-stone-400 mb-8">
            Manage integrations, imports, follow-up rules, tags, and your account.
          </p>
          <div className="flex items-center gap-2 text-sm text-stone-400 dark:text-stone-500 mt-12 justify-center">
            <RefreshCw className="w-4 h-4 animate-spin" />
            Loading accounts...
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-stone-50 dark:bg-stone-950">
      <div className="max-w-3xl mx-auto px-4 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-stone-900 dark:text-stone-100">Settings</h1>
          <p className="text-sm text-stone-500 dark:text-stone-400 mt-1">
            Manage integrations, imports, follow-up rules, tags, and your account.
          </p>
        </div>

        <TabBar activeTab={ctrl.activeTab} onChange={ctrl.setTab} />

        {ctrl.activeTab === "integrations" && (
          <div className="animate-in stagger-1"><IntegrationsTab
            connected={ctrl.connected}
            googleConnect={ctrl.googleConnect}
            googleSync={ctrl.googleSync}
            telegramConnect={ctrl.telegramConnect}
            telegramSync={ctrl.telegramSync}
            telegramSyncProgress={ctrl.telegramSyncProgress}
            twitterConnect={ctrl.twitterConnect}
            twitterSync={ctrl.twitterSync}
            showTelegramModal={ctrl.showTelegramModal}
            telegramFlow={telegramFlow}
            whatsappConnect={ctrl.whatsappConnect}
            whatsappSync={ctrl.whatsappSync}
            whatsappFlow={whatsappFlow}
            handleWhatsAppSync={ctrl.handleWhatsAppSync}
            fetchConnectionStatus={ctrl.fetchConnectionStatus}
            handleGoogleConnect={ctrl.handleGoogleConnect}
            handleGoogleSyncAll={ctrl.handleGoogleSyncAll}
            handleTelegramSync={ctrl.handleTelegramSync}
            handleTwitterConnect={ctrl.handleTwitterConnect}
            handleTwitterSync={ctrl.handleTwitterSync}
          />
          </div>
        )}
        {ctrl.activeTab === "import" && <div className="animate-in stagger-1"><ImportTab /></div>}
        {ctrl.activeTab === "followup" && <div className="animate-in stagger-1"><FollowUpRulesTab /></div>}
        {ctrl.activeTab === "tags" && <div className="animate-in stagger-1"><TagsTab /></div>}
        {ctrl.activeTab === "account" && <div className="animate-in stagger-1"><AccountTab /></div>}
      </div>

      {ctrl.successPlatform && (
        <SuccessModal
          platform={ctrl.successPlatform}
          onClose={() => ctrl.setSuccessPlatform(null)}
        />
      )}
    </div>
  );
}

/* ── Page export ── */
export default function SettingsPage() {
  return (
    <Suspense fallback={<Loading />}>
      <SettingsContent />
    </Suspense>
  );
}
