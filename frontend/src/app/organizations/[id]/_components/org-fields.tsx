"use client";

import { useState, useRef, useEffect } from "react";
import { Globe, Pencil, Users } from "lucide-react";

export function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Users;
  label: string;
  value: string | number;
}) {
  return (
    <div className="rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4">
      <div className="flex items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400">
        <Icon className="h-4 w-4" />
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">{value}</div>
    </div>
  );
}

export function OrgInlineField({
  icon: Icon,
  label,
  value,
  onSave,
  href,
}: {
  icon: typeof Globe;
  label: string;
  value: string | null;
  onSave: (v: string) => void;
  href?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!editing) setDraft(value ?? "");
  }, [value, editing]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const save = () => {
    if (draft !== (value ?? "")) onSave(draft);
    setEditing(false);
  };

  const cancel = () => {
    setDraft(value ?? "");
    setEditing(false);
  };

  return (
    <div className="group/field flex items-center gap-2 text-sm py-1">
      <Icon className="h-4 w-4 shrink-0 text-zinc-400 dark:text-zinc-500" />
      <span className="text-zinc-500 dark:text-zinc-400 shrink-0">{label}:</span>
      {editing ? (
        <div className="flex items-center gap-1.5 flex-1 min-w-0">
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") cancel(); }}
            onBlur={save}
            className="flex-1 min-w-0 text-sm rounded border border-zinc-300 dark:border-zinc-700 px-2 py-0.5 bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-teal-400"
          />
        </div>
      ) : (
        <div className="flex items-center gap-1.5 min-w-0 flex-1">
          {value ? (
            href ? (
              <a href={href} target="_blank" rel="noopener noreferrer" className="text-teal-600 dark:text-teal-400 hover:underline truncate">
                {value}
              </a>
            ) : (
              <span className="text-zinc-900 dark:text-zinc-100 truncate">{value}</span>
            )
          ) : (
            <span className="italic text-zinc-400 dark:text-zinc-500">—</span>
          )}
          <button
            onClick={() => { setDraft(value ?? ""); setEditing(true); }}
            className="p-0.5 rounded text-zinc-300 dark:text-zinc-600 hover:text-zinc-500 dark:hover:text-zinc-400 opacity-0 group-hover/field:opacity-100 transition-opacity shrink-0"
          >
            <Pencil className="w-3 h-3" />
          </button>
        </div>
      )}
    </div>
  );
}

export function OrgNotesField({ value, onSave }: { value: string | null; onSave: (v: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!editing) setDraft(value ?? "");
  }, [value, editing]);

  useEffect(() => {
    if (editing) textareaRef.current?.focus();
  }, [editing]);

  const save = () => {
    if (draft !== (value ?? "")) onSave(draft);
    setEditing(false);
  };

  const cancel = () => {
    setDraft(value ?? "");
    setEditing(false);
  };

  return (
    <div className="group/field mt-4">
      <label className="mb-1 block text-xs font-medium text-zinc-500 dark:text-zinc-400">Notes</label>
      {editing ? (
        <div className="space-y-2">
          <textarea
            ref={textareaRef}
            className="w-full rounded border border-zinc-300 dark:border-zinc-700 px-3 py-2 text-sm bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-teal-400"
            rows={3}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Escape") cancel(); }}
          />
          <div className="flex items-center gap-2 justify-end">
            <button onClick={cancel} className="px-2.5 py-1 text-xs font-medium rounded-md text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 border border-zinc-200 dark:border-zinc-700">Cancel</button>
            <button onClick={save} className="px-2.5 py-1 text-xs font-medium rounded-md bg-teal-600 text-white hover:bg-teal-700">Save</button>
          </div>
        </div>
      ) : (
        <div className="flex items-start gap-1.5">
          <p className="text-sm text-zinc-600 dark:text-zinc-400 flex-1">
            {value || <span className="italic text-zinc-400 dark:text-zinc-500">No notes</span>}
          </p>
          <button
            onClick={() => { setDraft(value ?? ""); setEditing(true); }}
            className="p-0.5 rounded text-zinc-300 dark:text-zinc-600 hover:text-zinc-500 dark:hover:text-zinc-400 opacity-0 group-hover/field:opacity-100 transition-opacity shrink-0 mt-0.5"
          >
            <Pencil className="w-3 h-3" />
          </button>
        </div>
      )}
    </div>
  );
}

export function OrgNameField({ value, onSave }: { value: string; onSave: (v: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const save = () => {
    if (draft.trim() && draft !== value) onSave(draft.trim());
    setEditing(false);
  };

  return (
    <div className="group/field flex items-center gap-2">
      {editing ? (
        <input
          ref={inputRef}
          className="rounded border border-zinc-300 dark:border-zinc-700 px-2 py-1 text-2xl font-bold bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-teal-400"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") { setDraft(value); setEditing(false); } }}
          onBlur={save}
        />
      ) : (
        <>
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">{value}</h1>
          <button
            onClick={() => { setDraft(value); setEditing(true); }}
            className="p-1 rounded text-zinc-300 dark:text-zinc-600 hover:text-zinc-500 dark:hover:text-zinc-400 opacity-0 group-hover/field:opacity-100 transition-opacity"
          >
            <Pencil className="w-4 h-4" />
          </button>
        </>
      )}
    </div>
  );
}
