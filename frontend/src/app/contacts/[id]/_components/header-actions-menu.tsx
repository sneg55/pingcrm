"use client";

import { useState, useRef, useEffect } from "react";
import {
  ArrowUpCircle,
  MoreVertical,
  RefreshCw,
  Sparkles,
  Trash2,
  Wand2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { Contact } from "@/hooks/use-contacts";

type HeaderActionsMenuProps = {
  contact: Contact;
  isRefreshing: boolean;
  isEnriching: boolean;
  isAutoTagging: boolean;
  is2ndTier: boolean;
  isPromoting?: boolean;
  onRefreshDetails: () => void;
  onEnrich: () => void;
  onAutoTag: () => void;
  onShowDeleteConfirm: () => void;
  onPromote?: () => void;
};

export function HeaderActionsMenu({
  contact,
  isRefreshing,
  isEnriching,
  isAutoTagging,
  is2ndTier,
  isPromoting,
  onRefreshDetails,
  onEnrich,
  onAutoTag,
  onShowDeleteConfirm,
  onPromote,
}: HeaderActionsMenuProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    if (menuOpen) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setMenuOpen((v) => !v)}
        className="btn-press p-2 rounded-lg text-stone-400 dark:text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
        title="More actions"
      >
        <MoreVertical className="w-4 h-4" />
      </button>
      {menuOpen && (
        <div className="menu-enter absolute right-0 top-full mt-1 w-52 bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 shadow-lg py-1 z-50">
          <button
            onClick={() => {
              setMenuOpen(false);
              onRefreshDetails();
            }}
            disabled={isRefreshing}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-stone-700 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 disabled:opacity-50"
          >
            <RefreshCw
              className={cn(
                "w-4 h-4 text-stone-400 dark:text-stone-500",
                isRefreshing && "animate-spin"
              )}
            />
            {isRefreshing ? "Refreshing..." : "Refresh details"}
          </button>
          <button
            onClick={() => {
              setMenuOpen(false);
              onEnrich();
            }}
            disabled={isEnriching || (!contact.emails?.length && !contact.linkedin_url)}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-stone-700 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 disabled:opacity-50"
          >
            <Sparkles
              className={cn(
                "w-4 h-4 text-amber-500",
                isEnriching && "animate-spin"
              )}
            />
            {isEnriching ? "Enriching..." : "Enrich with Apollo"}
          </button>
          <button
            onClick={() => {
              setMenuOpen(false);
              onAutoTag();
            }}
            disabled={isAutoTagging}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-stone-700 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 disabled:opacity-50"
          >
            <Wand2
              className={cn(
                "w-4 h-4 text-violet-500",
                isAutoTagging && "animate-spin"
              )}
            />
            {isAutoTagging ? "Tagging..." : "Auto-tag with AI"}
          </button>
          {is2ndTier && onPromote && (
            <button
              onClick={() => {
                setMenuOpen(false);
                onPromote();
              }}
              disabled={isPromoting}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-teal-600 dark:text-teal-400 hover:bg-teal-50 dark:hover:bg-teal-950 disabled:opacity-50"
            >
              <ArrowUpCircle className="w-4 h-4" />
              {isPromoting ? "Promoting..." : "Promote to 1st Tier"}
            </button>
          )}
          <div className="my-1 h-px bg-stone-100 dark:bg-stone-800" />
          <button
            onClick={() => {
              setMenuOpen(false);
              onShowDeleteConfirm();
            }}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-950"
          >
            <Trash2 className="w-4 h-4" /> Delete contact
          </button>
        </div>
      )}
    </div>
  );
}
