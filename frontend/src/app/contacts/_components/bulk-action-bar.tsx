"use client";

import { useState } from "react";
import { Archive, Building2, GitMerge, SlidersHorizontal, Tag, Trash2, X } from "lucide-react";

export function BulkActionBar({
  selectedCount,
  allTags,
  onAddTag,
  onRemoveTag,
  onArchive,
  onDelete,
  onMerge,
  onSetPriority,
  onSetCompany,
  onClear,
  isPending,
}: {
  selectedCount: number;
  allTags: string[];
  onAddTag: (tag: string) => void;
  onRemoveTag: (tag: string) => void;
  onArchive: () => void;
  onDelete: () => void;
  onMerge: () => void;
  onSetPriority: (level: string) => void;
  onSetCompany: (company: string) => void;
  onClear: () => void;
  isPending: boolean;
}) {
  const [tagInput, setTagInput] = useState("");
  const [showTagDropdown, setShowTagDropdown] = useState(false);
  const [tagMode, setTagMode] = useState<"add" | "remove">("add");
  const [showPriorityDropdown, setShowPriorityDropdown] = useState(false);
  const [showCompanyInput, setShowCompanyInput] = useState(false);
  const [companyInput, setCompanyInput] = useState("");

  const filteredTags = allTags.filter(
    (t) => !tagInput || t.toLowerCase().includes(tagInput.toLowerCase())
  );

  return (
    <div className="sticky bottom-4 z-30 mx-auto w-fit bg-stone-900 text-white rounded-xl shadow-2xl px-5 py-3 flex items-center gap-4">
      <span className="text-sm font-medium">
        <span className="font-mono-data">{selectedCount}</span> selected
      </span>
      <div className="w-px h-5 bg-stone-700" />

      <div className="relative">
        <div className="flex items-center gap-1">
          <button
            onClick={() => { setTagMode("add"); setShowTagDropdown((v) => !v); }}
            disabled={isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-stone-800 hover:bg-stone-700 transition-colors disabled:opacity-50"
          >
            <Tag className="w-3.5 h-3.5" /> Add Tag
          </button>
          <button
            onClick={() => { setTagMode("remove"); setShowTagDropdown((v) => !v); }}
            disabled={isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-stone-800 hover:bg-stone-700 transition-colors disabled:opacity-50"
          >
            <X className="w-3.5 h-3.5" /> Remove Tag
          </button>
        </div>
        {showTagDropdown && (
          <div className="absolute left-0 bottom-full mb-1 w-56 bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 shadow-lg z-50 p-2">
            <input
              type="text"
              placeholder={tagMode === "add" ? "Type tag name..." : "Select tag to remove..."}
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && tagInput.trim() && tagMode === "add") {
                  onAddTag(tagInput.trim());
                  setTagInput("");
                  setShowTagDropdown(false);
                }
              }}
              className="w-full px-2.5 py-1.5 text-sm text-stone-900 dark:text-stone-100 rounded-md border border-stone-300 dark:border-stone-700 focus:outline-none focus:ring-2 focus:ring-teal-400 mb-1 bg-white dark:bg-stone-800 placeholder:text-stone-400 dark:placeholder:text-stone-500"
              autoFocus
            />
            <div className="max-h-32 overflow-y-auto">
              {filteredTags.map((tag) => (
                <button
                  key={tag}
                  onClick={() => {
                    if (tagMode === "add") onAddTag(tag);
                    else onRemoveTag(tag);
                    setTagInput("");
                    setShowTagDropdown(false);
                  }}
                  className="w-full text-left px-2.5 py-1.5 text-sm text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 rounded-md"
                >
                  {tagMode === "add" ? "+" : "-"} {tag}
                </button>
              ))}
              {tagMode === "add" && tagInput.trim() && !allTags.includes(tagInput.trim()) && (
                <button
                  onClick={() => {
                    onAddTag(tagInput.trim());
                    setTagInput("");
                    setShowTagDropdown(false);
                  }}
                  className="w-full text-left px-2.5 py-1.5 text-sm text-teal-600 dark:text-teal-400 hover:bg-teal-50 dark:hover:bg-teal-950 rounded-md font-medium"
                >
                  + Create &quot;{tagInput.trim()}&quot;
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="relative">
        <button
          onClick={() => { setShowPriorityDropdown((v) => !v); setShowCompanyInput(false); setShowTagDropdown(false); }}
          disabled={isPending}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-stone-800 hover:bg-stone-700 transition-colors disabled:opacity-50"
        >
          <SlidersHorizontal className="w-3.5 h-3.5" /> Priority
        </button>
        {showPriorityDropdown && (
          <div className="absolute left-0 bottom-full mb-1 w-40 bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 shadow-lg z-50 p-1">
            {[
              { value: "high", label: "High", color: "text-red-600 dark:text-red-400" },
              { value: "medium", label: "Medium", color: "text-stone-700 dark:text-stone-300" },
              { value: "low", label: "Low", color: "text-stone-400 dark:text-stone-500" },
            ].map((opt) => (
              <button
                key={opt.value}
                onClick={() => { onSetPriority(opt.value); setShowPriorityDropdown(false); }}
                className={`w-full text-left px-2.5 py-1.5 text-sm ${opt.color} hover:bg-stone-100 dark:hover:bg-stone-800 rounded-md`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="relative">
        <button
          onClick={() => { setShowCompanyInput((v) => !v); setShowPriorityDropdown(false); setShowTagDropdown(false); }}
          disabled={isPending}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-stone-800 hover:bg-stone-700 transition-colors disabled:opacity-50"
        >
          <Building2 className="w-3.5 h-3.5" /> Company
        </button>
        {showCompanyInput && (
          <div className="absolute left-0 bottom-full mb-1 w-56 bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 shadow-lg z-50 p-2">
            <input
              type="text"
              placeholder="Set company name..."
              value={companyInput}
              onChange={(e) => setCompanyInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && companyInput.trim()) {
                  onSetCompany(companyInput.trim());
                  setCompanyInput("");
                  setShowCompanyInput(false);
                }
              }}
              className="w-full px-2.5 py-1.5 text-sm text-stone-900 dark:text-stone-100 rounded-md border border-stone-300 dark:border-stone-700 focus:outline-none focus:ring-2 focus:ring-teal-400 bg-white dark:bg-stone-800 placeholder:text-stone-400 dark:placeholder:text-stone-500"
              autoFocus
            />
          </div>
        )}
      </div>

      {selectedCount >= 2 && (
        <button
          onClick={onMerge}
          disabled={isPending}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-stone-800 hover:bg-stone-700 transition-colors disabled:opacity-50"
        >
          <GitMerge className="w-3.5 h-3.5" /> Merge
        </button>
      )}

      <button
        onClick={onArchive}
        disabled={isPending}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-stone-800 hover:bg-stone-700 transition-colors disabled:opacity-50"
      >
        <Archive className="w-3.5 h-3.5" /> Archive
      </button>

      <button
        onClick={onDelete}
        disabled={isPending}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-red-600 hover:bg-red-700 transition-colors disabled:opacity-50"
      >
        <Trash2 className="w-3.5 h-3.5" /> Delete
      </button>

      <button
        onClick={onClear}
        className="p-1.5 rounded-lg hover:bg-stone-700 text-stone-400 transition-colors ml-1"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

export function Pagination({
  page,
  totalPages,
  total,
  pageSize,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
  onPageChange: (p: number) => void;
}) {
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  const pages: Array<number | "..."> = [];
  if (totalPages <= 5) {
    for (let i = 1; i <= totalPages; i++) pages.push(i);
  } else {
    pages.push(1);
    if (page > 3) pages.push("...");
    for (let i = Math.max(2, page - 1); i <= Math.min(totalPages - 1, page + 1); i++) pages.push(i);
    if (page < totalPages - 2) pages.push("...");
    pages.push(totalPages);
  }

  return (
    <div className="flex items-center justify-between mt-4">
      <p className="text-xs text-stone-500 dark:text-stone-400">
        Showing <strong>{from}-{to}</strong> of <strong>{total}</strong>
      </p>
      <div className="flex items-center gap-1.5">
        <button
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="px-3 py-1.5 text-xs font-medium rounded-lg border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 disabled:text-stone-300 dark:disabled:text-stone-600 disabled:bg-stone-50 dark:disabled:bg-stone-900 disabled:cursor-not-allowed transition-colors"
        >
          Previous
        </button>
        {pages.map((p, i) =>
          p === "..." ? (
            <span key={`dots-${i}`} className="text-xs text-stone-400 dark:text-stone-500 px-1">...</span>
          ) : (
            <button
              key={p}
              onClick={() => onPageChange(p)}
              className={`px-2.5 py-1.5 text-xs font-medium rounded-lg min-w-[32px] text-center transition-colors ${
                p === page
                  ? "bg-teal-600 text-white"
                  : "border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
              }`}
            >
              {p}
            </button>
          )
        )}
        <button
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          className="px-3 py-1.5 text-xs font-medium rounded-lg border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800 disabled:text-stone-300 dark:disabled:text-stone-600 disabled:bg-stone-50 dark:disabled:bg-stone-900 disabled:cursor-not-allowed transition-colors"
        >
          Next
        </button>
      </div>
    </div>
  );
}
