"use client";

import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

type AvatarModalProps = {
  avatarUrl: string;
  displayName: string;
};

export function AvatarModal({ avatarUrl, displayName }: AvatarModalProps) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="cursor-zoom-in"
        title="View full photo"
      >
        <img
          src={avatarUrl}
          alt={displayName}
          className="w-20 h-20 rounded-full object-cover hover:ring-2 hover:ring-teal-400 transition-all"
        />
      </button>

      {open &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60"
            onClick={() => setOpen(false)}
          >
            <div
              className="relative bg-white dark:bg-stone-900 rounded-2xl shadow-2xl p-6 max-w-lg w-full mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                onClick={() => setOpen(false)}
                className="absolute top-3 right-3 p-1.5 rounded-full text-stone-400 hover:text-stone-600 hover:bg-stone-100 dark:text-stone-500 dark:hover:text-stone-300 dark:hover:bg-stone-800 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
              <img
                src={avatarUrl}
                alt={displayName}
                className="w-full rounded-xl object-contain"
              />
              <p className="text-center text-sm font-medium text-stone-700 dark:text-stone-300 mt-3">
                {displayName}
              </p>
            </div>
          </div>,
          document.body
        )}
    </>
  );
}
