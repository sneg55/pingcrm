"use client";

import { X, Plus } from "lucide-react";

type CategoryCardProps = {
  category: string;
  tags: string[];
  isEditing: boolean;
  newTagValue: string;
  onNewTagChange: (value: string) => void;
  onAddTag: (category: string) => void;
  onRemoveTag: (category: string, tag: string) => void;
  onRemoveCategory: (category: string) => void;
};

export function CategoryCard({
  category,
  tags,
  isEditing,
  newTagValue,
  onNewTagChange,
  onAddTag,
  onRemoveTag,
  onRemoveCategory,
}: CategoryCardProps) {
  return (
    <div className="bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-stone-700 dark:text-stone-300">{category}</h3>
        {isEditing && (
          <button
            onClick={() => onRemoveCategory(category)}
            className="text-xs text-red-500 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 transition-colors"
          >
            Remove category
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        {tags.map((tag) => (
          <span
            key={tag}
            className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm ${
              isEditing
                ? "bg-stone-100 dark:bg-stone-800 text-stone-700 dark:text-stone-300 pr-1.5"
                : "bg-teal-50 dark:bg-teal-950 text-teal-700 dark:text-teal-400 border border-teal-200 dark:border-teal-800"
            }`}
          >
            {tag}
            {isEditing && (
              <button
                onClick={() => onRemoveTag(category, tag)}
                className="p-0.5 rounded-full hover:bg-stone-200 dark:hover:bg-stone-700 transition-colors"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </span>
        ))}
        {isEditing && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              onAddTag(category);
            }}
            className="inline-flex items-center"
          >
            <input
              type="text"
              value={newTagValue}
              onChange={(e) => onNewTagChange(e.target.value)}
              placeholder="Add tag..."
              className="w-28 px-2 py-1 text-sm rounded-md border border-stone-200 dark:border-stone-700 focus:outline-none focus:ring-1 focus:ring-teal-500 focus:border-teal-500 bg-white dark:bg-stone-900 text-stone-900 dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
            />
            <button
              type="submit"
              className="ml-1 p-1 rounded-md hover:bg-stone-100 dark:hover:bg-stone-800 text-stone-400 dark:text-stone-500 hover:text-teal-600 dark:hover:text-teal-400 transition-colors"
            >
              <Plus className="w-4 h-4" />
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
