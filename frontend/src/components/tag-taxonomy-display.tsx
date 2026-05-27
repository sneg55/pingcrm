"use client";

import { Plus, Check, RotateCcw } from "lucide-react";
import { CategoryCard } from "./tag-taxonomy-category-card";

type SaveMutationArg = { cats: Record<string, string[]>; newStatus?: string };
type TaxonomyStatus = "draft" | "approved";

type TaxonomyDisplayProps = {
  taxonomyStatus: TaxonomyStatus;
  categories: Record<string, string[]>;
  isEditing: boolean;
  editCategories: Record<string, string[]> | null;
  newTagInputs: Record<string, string>;
  newCategoryName: string;
  isDiscovering: boolean;
  isSavePending: boolean;
  onSetNewTagInputs: (inputs: Record<string, string>) => void;
  onSetNewCategoryName: (name: string) => void;
  onSetEditCategories: (cats: Record<string, string[]> | null) => void;
  onStartEditing: () => void;
  onAddTag: (category: string) => void;
  onRemoveTag: (category: string, tag: string) => void;
  onRemoveCategory: (category: string) => void;
  onAddCategory: () => void;
  onDiscover: () => void;
  onSave: (arg: SaveMutationArg) => void;
};

export function TaxonomyDisplay({
  taxonomyStatus,
  categories,
  isEditing,
  editCategories,
  newTagInputs,
  newCategoryName,
  isDiscovering,
  isSavePending,
  onSetNewTagInputs,
  onSetNewCategoryName,
  onSetEditCategories,
  onStartEditing,
  onAddTag,
  onRemoveTag,
  onRemoveCategory,
  onAddCategory,
  onDiscover,
  onSave,
}: TaxonomyDisplayProps) {
  return (
    <div className="space-y-4">
      {taxonomyStatus === "draft" && (
        <div className="bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-lg p-4 flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-amber-800 dark:text-amber-400">Draft Taxonomy</p>
            <p className="text-xs text-amber-600 dark:text-amber-500 mt-0.5">
              Review and edit the proposed tags, then approve to start tagging contacts.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={onDiscover}
              disabled={isDiscovering}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md border border-amber-300 dark:border-amber-700 text-amber-700 dark:text-amber-400 hover:bg-amber-100 dark:hover:bg-amber-900 transition-colors disabled:opacity-50"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Re-discover
            </button>
            {!isEditing && (
              <button
                onClick={onStartEditing}
                className="px-3 py-1.5 text-sm font-medium rounded-md border border-amber-300 dark:border-amber-700 text-amber-700 dark:text-amber-400 hover:bg-amber-100 dark:hover:bg-amber-900 transition-colors"
              >
                Edit
              </button>
            )}
            <button
              onClick={() => {
                const cats = editCategories || categories;
                onSave({ cats, newStatus: "approved" });
              }}
              disabled={isSavePending}
              className="px-4 py-1.5 text-sm font-medium rounded-md bg-teal-600 text-white hover:bg-teal-700 disabled:opacity-50 transition-colors"
            >
              {isSavePending ? "Saving..." : "Approve Taxonomy"}
            </button>
          </div>
        </div>
      )}

      {taxonomyStatus === "approved" && !isEditing && (
        <div className="bg-teal-50 dark:bg-teal-950 border border-teal-200 dark:border-teal-800 rounded-lg p-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Check className="w-4 h-4 text-teal-600 dark:text-teal-400" />
            <p className="text-sm font-medium text-teal-800 dark:text-teal-300">Approved Taxonomy</p>
          </div>
          <button
            onClick={onStartEditing}
            className="px-3 py-1.5 text-sm font-medium rounded-md border border-teal-300 dark:border-teal-700 text-teal-700 dark:text-teal-400 hover:bg-teal-100 dark:hover:bg-teal-900 transition-colors"
          >
            Edit
          </button>
        </div>
      )}

      {isEditing && (
        <div className="flex items-center gap-2 justify-end">
          <button
            onClick={() => onSetEditCategories(null)}
            className="px-3 py-1.5 text-sm rounded-md border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => {
              if (editCategories) {
                onSave({ cats: editCategories, newStatus: "approved" });
              }
            }}
            disabled={isSavePending}
            className="px-4 py-1.5 text-sm font-medium rounded-md bg-teal-600 text-white hover:bg-teal-700 disabled:opacity-50 transition-colors"
          >
            {isSavePending ? "Saving..." : "Approve Taxonomy"}
          </button>
        </div>
      )}

      {Object.entries(categories).map(([category, tags]) => (
        <CategoryCard
          key={category}
          category={category}
          tags={tags}
          isEditing={isEditing}
          newTagValue={newTagInputs[category] || ""}
          onNewTagChange={(value) =>
            onSetNewTagInputs({ ...newTagInputs, [category]: value })
          }
          onAddTag={onAddTag}
          onRemoveTag={onRemoveTag}
          onRemoveCategory={onRemoveCategory}
        />
      ))}

      {isEditing && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onAddCategory();
          }}
          className="flex items-center gap-2"
        >
          <input
            type="text"
            value={newCategoryName}
            onChange={(e) => onSetNewCategoryName(e.target.value)}
            placeholder="New category name..."
            className="flex-1 px-3 py-2 text-sm rounded-lg border border-dashed border-stone-300 dark:border-stone-600 focus:outline-none focus:ring-1 focus:ring-teal-500 focus:border-teal-500 bg-white dark:bg-stone-900 text-stone-900 dark:text-stone-100 placeholder:text-stone-400 dark:placeholder:text-stone-500"
          />
          <button
            type="submit"
            disabled={!newCategoryName.trim()}
            className="px-4 py-2 text-sm font-medium rounded-lg border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 disabled:opacity-50 transition-colors"
          >
            <Plus className="w-4 h-4" />
          </button>
        </form>
      )}
    </div>
  );
}
