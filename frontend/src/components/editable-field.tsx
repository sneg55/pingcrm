"use client";

import { useState, useRef, useEffect } from "react";
import { Pencil } from "lucide-react";
import { cn } from "@/lib/utils";

interface EditableFieldProps {
  label: string;
  value: string | null | undefined;
  onSave: (value: string) => void;
  placeholder?: string;
  type?: "text" | "textarea" | "date";
  icon?: React.ReactNode;
  linkPrefix?: string;
  className?: string;
}

export function EditableField({
  label,
  value,
  onSave,
  placeholder = "Add...",
  type = "text",
  icon,
  linkPrefix,
  className,
}: EditableFieldProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null);

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
    }
  }, [editing]);

  useEffect(() => {
    setDraft(value ?? "");
  }, [value]);

  const handleSave = () => {
    const trimmed = draft.trim();
    if (trimmed !== (value ?? "")) {
      onSave(trimmed);
    }
    setEditing(false);
  };

  const handleCancel = () => {
    setDraft(value ?? "");
    setEditing(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && type !== "textarea") {
      e.preventDefault();
      handleSave();
    }
    if (e.key === "Escape") {
      handleCancel();
    }
  };

  const displayValue = value || null;

  return (
    <div
      className={cn(
        "group flex items-start gap-3 py-2.5 px-3 -mx-3 rounded-lg transition-colors",
        !editing && "hover:bg-gray-50 cursor-pointer",
        className
      )}
      onClick={() => !editing && setEditing(true)}
    >
      {icon && (
        <span className="mt-0.5 text-gray-400 flex-shrink-0">{icon}</span>
      )}
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-0.5">
          {label}
        </p>
        {editing ? (
          <div>
            {type === "textarea" ? (
              <textarea
                ref={inputRef as React.RefObject<HTMLTextAreaElement>}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={handleKeyDown}
                onBlur={handleSave}
                rows={3}
                className="w-full text-sm border border-gray-300 rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-400 resize-none"
                placeholder={placeholder}
              />
            ) : (
              <input
                ref={inputRef as React.RefObject<HTMLInputElement>}
                type={type === "date" ? "date" : "text"}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={handleKeyDown}
                onBlur={handleSave}
                className="w-full text-sm border border-gray-300 rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-400"
                placeholder={placeholder}
              />
            )}
          </div>
        ) : (
          <div className="flex items-center gap-1.5">
            {displayValue ? (
              linkPrefix !== undefined ? (
                <a
                  href={`${linkPrefix}${displayValue}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm text-blue-600 hover:underline truncate"
                  onClick={(e) => e.stopPropagation()}
                >
                  {displayValue}
                </a>
              ) : (
                <span className="text-sm text-gray-900 truncate">
                  {displayValue}
                </span>
              )
            ) : (
              <span className="text-sm text-gray-300 italic">{placeholder}</span>
            )}
            <Pencil className="w-3 h-3 text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
          </div>
        )}
      </div>
    </div>
  );
}

interface EditableListFieldProps {
  label: string;
  values: string[];
  onSave: (values: string[]) => void;
  placeholder?: string;
  icon?: React.ReactNode;
  linkPrefix?: string;
}

export function EditableListField({
  label,
  values,
  onSave,
  placeholder = "Add...",
  icon,
  linkPrefix,
}: EditableListFieldProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(values.join(", "));
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  useEffect(() => {
    setDraft(values.join(", "));
  }, [values]);

  const handleSave = () => {
    const parsed = draft
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    onSave(parsed);
    setEditing(false);
  };

  const handleCancel = () => {
    setDraft(values.join(", "));
    setEditing(false);
  };

  return (
    <div
      className={cn(
        "group flex items-start gap-3 py-2.5 px-3 -mx-3 rounded-lg transition-colors",
        !editing && "hover:bg-gray-50 cursor-pointer"
      )}
      onClick={() => !editing && setEditing(true)}
    >
      {icon && (
        <span className="mt-0.5 text-gray-400 flex-shrink-0">{icon}</span>
      )}
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-0.5">
          {label}
        </p>
        {editing ? (
          <div>
            <input
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleSave();
                }
                if (e.key === "Escape") handleCancel();
              }}
              onBlur={handleSave}
              className="w-full text-sm border border-gray-300 rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-400"
              placeholder="Comma-separated values"
            />
          </div>
        ) : (
          <div className="flex items-center gap-1.5">
            {values.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {values.map((v) =>
                  linkPrefix ? (
                    <a
                      key={v}
                      href={`${linkPrefix}${v}`}
                      className="text-sm text-blue-600 hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {v}
                    </a>
                  ) : (
                    <span key={v} className="text-sm text-gray-900">
                      {v}
                    </span>
                  )
                )}
              </div>
            ) : (
              <span className="text-sm text-gray-300 italic">{placeholder}</span>
            )}
            <Pencil className="w-3 h-3 text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
          </div>
        )}
      </div>
    </div>
  );
}

interface EditableTagsFieldProps {
  label: string;
  values: string[];
  onSave: (values: string[]) => void;
  icon?: React.ReactNode;
  allTags?: string[];
}

export function EditableTagsField({
  label,
  values,
  onSave,
  icon,
  allTags = [],
}: EditableTagsFieldProps) {
  const [editing, setEditing] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>(values);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  useEffect(() => {
    setSelectedTags(values);
  }, [values]);

  const handleOpen = () => {
    setEditing(true);
    setInputValue("");
    setSelectedTags(values);
  };

  const handleClose = () => {
    // Save on close
    const deduplicated = [...new Set(selectedTags)];
    if (JSON.stringify(deduplicated) !== JSON.stringify(values)) {
      onSave(deduplicated);
    }
    setEditing(false);
    setInputValue("");
  };

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  };

  const addNewTag = () => {
    const tag = inputValue.trim();
    if (tag && !selectedTags.includes(tag)) {
      setSelectedTags((prev) => [...prev, tag]);
    }
    setInputValue("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (inputValue.trim()) {
        addNewTag();
      } else {
        handleClose();
      }
    }
    if (e.key === "Escape") {
      setSelectedTags(values);
      setEditing(false);
      setInputValue("");
    }
    if (e.key === "Backspace" && !inputValue && selectedTags.length > 0) {
      setSelectedTags((prev) => prev.slice(0, -1));
    }
  };

  // Filter suggestions: existing tags not yet selected, matching input
  const suggestions = allTags.filter(
    (t) =>
      !selectedTags.includes(t) &&
      t.toLowerCase().includes(inputValue.toLowerCase())
  );

  return (
    <div
      className={cn(
        "group flex items-start gap-3 py-2.5 px-3 -mx-3 rounded-lg transition-colors",
        !editing && "hover:bg-gray-50 cursor-pointer"
      )}
      onClick={() => !editing && handleOpen()}
    >
      {icon && (
        <span className="mt-0.5 text-gray-400 flex-shrink-0">{icon}</span>
      )}
      <div className="flex-1 min-w-0" ref={containerRef}>
        <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-0.5">
          {label}
        </p>
        {editing ? (
          <div>
            {/* Selected tags as chips */}
            <div className="flex flex-wrap gap-1 mb-1.5">
              {selectedTags.map((tag) => (
                <button
                  key={tag}
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleTag(tag);
                  }}
                  className="inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-xs bg-blue-100 text-blue-700 border border-blue-200 hover:bg-red-50 hover:text-red-600 hover:border-red-200 transition-colors"
                >
                  {tag}
                  <span className="text-[10px]">×</span>
                </button>
              ))}
            </div>
            {/* Input for new tag */}
            <input
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              onBlur={handleClose}
              className="w-full text-sm border border-gray-300 rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-400"
              placeholder={selectedTags.length > 0 ? "Add more..." : "Type to add label..."}
            />
            {/* Suggestions dropdown */}
            {(suggestions.length > 0 || (inputValue.trim() && !allTags.includes(inputValue.trim()) && !selectedTags.includes(inputValue.trim()))) && (
              <div className="mt-1 border border-gray-200 rounded-md bg-white shadow-sm max-h-32 overflow-y-auto">
                {suggestions.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    onMouseDown={(e) => {
                      e.preventDefault(); // prevent blur
                      toggleTag(tag);
                      setInputValue("");
                    }}
                    className="w-full text-left px-2 py-1.5 text-sm hover:bg-blue-50 text-gray-700"
                  >
                    {tag}
                  </button>
                ))}
                {inputValue.trim() && !allTags.includes(inputValue.trim()) && !selectedTags.includes(inputValue.trim()) && (
                  <button
                    type="button"
                    onMouseDown={(e) => {
                      e.preventDefault();
                      addNewTag();
                    }}
                    className="w-full text-left px-2 py-1.5 text-sm hover:bg-green-50 text-green-700"
                  >
                    Create &quot;{inputValue.trim()}&quot;
                  </button>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-1.5">
            {values.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {values.map((tag) => (
                  <span
                    key={tag}
                    className="inline-block px-2 py-0.5 rounded-full text-xs bg-blue-50 text-blue-700 border border-blue-100"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            ) : (
              <span className="text-sm text-gray-300 italic">Add labels...</span>
            )}
            <Pencil className="w-3 h-3 text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
          </div>
        )}
      </div>
    </div>
  );
}
