"use client";

import { Check, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { SyncResultPanel } from "../shared";
import type { SyncState } from "../../_hooks/use-settings-controller";

type GoogleStatusBannersProps = {
  googleConnect: SyncState;
  googleSync: SyncState;
};

export function GoogleStatusBanners({ googleConnect, googleSync }: GoogleStatusBannersProps) {
  return (
    <>
      {googleConnect.message && (
        <p
          className={cn(
            "text-xs mt-3 flex items-center gap-1",
            googleConnect.status === "error" ? "text-red-500" : "text-emerald-600 dark:text-emerald-400"
          )}
        >
          {googleConnect.status === "error" ? (
            <AlertCircle className="w-3 h-3" />
          ) : (
            <Check className="w-3 h-3" />
          )}
          {googleConnect.message}
        </p>
      )}
      {googleSync.message && !googleSync.details && (
        <p
          className={cn(
            "text-xs mt-3 flex items-center gap-1",
            googleSync.status === "error" ? "text-red-500" : "text-emerald-600 dark:text-emerald-400"
          )}
        >
          {googleSync.status === "error" ? (
            <AlertCircle className="w-3 h-3" />
          ) : (
            <Check className="w-3 h-3" />
          )}
          {googleSync.message}
        </p>
      )}
      {googleSync.details && (
        <SyncResultPanel details={googleSync.details} status={googleSync.status} />
      )}
    </>
  );
}
