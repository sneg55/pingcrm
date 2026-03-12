"use client";

import { useState, useRef, useEffect } from "react";
import { Pencil } from "lucide-react";

/* ── CopyButton (inline, no external dep) ── */
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button
      onClick={copy}
      aria-label="Copy"
      className="p-0.5 rounded text-stone-300 hover:text-stone-500 transition-colors shrink-0"
    >
      {copied ? "✓" : "⧉"}
    </button>
  );
}

/* ── InlineListField ── */

export interface InlineListFieldProps {
  label: string;
  values: string[];
  onSave: (v: string[]) => void;
  copyable?: boolean;
  isLink?: boolean;
  linkPrefix?: string;
}

export function InlineListField({
  label,
  values,
  onSave,
  copyable,
  isLink,
  linkPrefix,
}: InlineListFieldProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(values.join(", "));
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const save = () => {
    const newValues = draft
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    onSave(newValues);
    setEditing(false);
  };

  const cancel = () => {
    setDraft(values.join(", "));
    setEditing(false);
  };

  const startEdit = () => {
    setDraft(values.join(", "));
    setEditing(true);
  };

  const displayValue = values[0] || null;

  return (
    <div className="group/row flex items-start justify-between gap-4 py-1.5">
      <span className="text-xs text-stone-500 shrink-0 mt-0.5">{label}</span>
      {editing ? (
        <div className="flex flex-col items-end gap-1.5 min-w-0 flex-1">
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") save();
              if (e.key === "Escape") cancel();
            }}
            className="w-full text-xs border border-stone-300 rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-teal-400 bg-white"
          />
          <div className="flex items-center gap-2">
            <button
              onClick={cancel}
              className="px-2.5 py-1 text-xs font-medium rounded-md text-stone-600 hover:bg-stone-100 border border-stone-200"
            >
              Cancel
            </button>
            <button
              onClick={save}
              className="px-2.5 py-1 text-xs font-medium rounded-md bg-emerald-600 text-white hover:bg-emerald-700"
            >
              Save
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-1.5 min-w-0">
          {displayValue ? (
            isLink && linkPrefix ? (
              <a
                href={`${linkPrefix}${displayValue}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs font-medium text-teal-600 hover:text-teal-700 truncate"
              >
                {displayValue}
              </a>
            ) : (
              <span className="text-xs font-medium text-stone-900 truncate">
                {displayValue}
                {values.length > 1 && (
                  <span className="text-stone-400 ml-1">
                    +{values.length - 1}
                  </span>
                )}
              </span>
            )
          ) : (
            <span className="text-xs text-stone-400">—</span>
          )}
          {copyable && displayValue && <CopyButton text={displayValue} />}
          <button
            onClick={startEdit}
            aria-label="Edit"
            className="p-0.5 rounded text-stone-300 hover:text-stone-500 opacity-0 group-hover/row:opacity-100 transition-opacity shrink-0"
          >
            <Pencil className="w-3 h-3" />
          </button>
        </div>
      )}
    </div>
  );
}
