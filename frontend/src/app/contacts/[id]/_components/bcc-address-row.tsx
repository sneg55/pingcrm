"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";

export function BccAddressRow({ address }: { address: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="group/row flex items-center justify-between py-1.5 px-1 -mx-1 rounded hover:bg-stone-50 dark:hover:bg-stone-800/50">
      <span className="text-xs text-stone-400 dark:text-stone-500 w-24 shrink-0">BCC log</span>
      <div className="flex items-center gap-1.5 min-w-0 flex-1">
        <span className="text-xs text-stone-500 dark:text-stone-400 truncate" title={address}>
          {address}
        </span>
        <button
          onClick={() => {
            void navigator.clipboard.writeText(address);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
          className={cn(
            "p-0.5 rounded transition-all shrink-0",
            copied
              ? "text-emerald-500"
              : "text-stone-300 dark:text-stone-600 hover:text-stone-500 dark:hover:text-stone-400 opacity-0 group-hover/row:opacity-100"
          )}
          title="Copy BCC address"
        >
          {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
        </button>
      </div>
    </div>
  );
}
