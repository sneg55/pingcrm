"use client";

import { useState } from "react";
import { StickyNote } from "lucide-react";

export function AddNoteInput({ onSave }: { onSave: (content: string) => void }) {
  const [focused, setFocused] = useState(false);
  const [text, setText] = useState("");

  const handleSave = () => {
    if (!text.trim()) return;
    onSave(text.trim());
    setText("");
    setFocused(false);
  };

  return (
    <div className="bg-white rounded-xl border border-stone-200 p-3 flex items-start gap-3">
      <StickyNote className="w-4 h-4 text-amber-400 mt-1.5 shrink-0" />
      <div className="flex-1">
        <textarea
          rows={focused ? 3 : 1}
          placeholder="Add a note..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          onFocus={() => setFocused(true)}
          className="w-full text-sm border-0 resize-none focus:outline-none placeholder:text-stone-400 py-1"
        />
        {focused && (
          <div className="flex items-center justify-end gap-2 mt-2 pt-2 border-t border-stone-100">
            <button
              onClick={() => {
                setText("");
                setFocused(false);
              }}
              className="px-3 py-1.5 text-xs text-stone-500 hover:bg-stone-50 rounded-md transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              className="px-3 py-1.5 text-xs font-medium rounded-md bg-teal-600 text-white hover:bg-teal-700 transition-colors"
            >
              Save note
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
