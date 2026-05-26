"use client";

import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { Tag, X, Loader2, Wand2, Check, RotateCcw, AlertCircle } from "lucide-react";
import { client } from "@/lib/api-client";
import { useTaxonomyMutations, useTaxonomyEditing } from "./tag-taxonomy-mutations";
import { TaxonomyDisplay } from "./tag-taxonomy-display";
import type { StatusMsg } from "./tag-taxonomy-mutations";

type TaxonomyResult = {
  categories: Record<string, string[]>;
  total_tags: number;
  status: "draft" | "approved";
}

function narrowTaxonomy(raw: { categories: Record<string, string[]>; total_tags: number; status: string } | null | undefined): TaxonomyResult | null {
  if (!raw) return null;
  return {
    categories: raw.categories,
    total_tags: raw.total_tags,
    status: raw.status === "approved" ? "approved" : "draft",
  };
}

async function fetchTaxonomy(): Promise<TaxonomyResult | null> {
  const { data, error } = await client.GET("/api/v1/contacts/tags/taxonomy", {});
  if (error) return null;
  return narrowTaxonomy(data?.data);
}

function ElapsedTimer({ running }: { running: boolean }) {
  const [elapsed, setElapsed] = useState(0);
  const startRef = useRef(Date.now());

  useEffect(() => {
    if (!running) {
      setElapsed(0);
      return;
    }
    startRef.current = Date.now();
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startRef.current) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [running]);

  if (!running || elapsed < 3) return null;
  return (
    <span className="text-xs text-stone-400 dark:text-stone-500 mt-2 block">
      {elapsed}s elapsed — this can take up to a minute for large contact lists
    </span>
  );
}

type StatusBannerProps = {
  statusMsg: StatusMsg;
  onDismiss: () => void;
};

function resolveCategories(
  editCategories: Record<string, string[]> | null,
  taxonomy: TaxonomyResult | null | undefined
): Record<string, string[]> {
  if (editCategories !== null) return editCategories;
  if (taxonomy?.categories) return taxonomy.categories;
  return {};
}

function getPanelSubtitle(
  hasTaxonomy: boolean,
  isDiscovering: boolean,
  totalTags: number,
  categoryCount: number
): string {
  if (hasTaxonomy && !isDiscovering) return `${totalTags} tags across ${categoryCount} categories`;
  if (isDiscovering) return "Scanning contacts...";
  return "Discover tags from your contacts using AI";
}

function StatusBanner({ statusMsg, onDismiss }: StatusBannerProps) {
  const isSuccess = statusMsg.type === "success";
  return (
    <div className={`mb-4 px-4 py-3 rounded-lg text-sm flex items-center gap-2 ${
      isSuccess
        ? "bg-green-50 dark:bg-emerald-950 border border-green-200 dark:border-emerald-800 text-green-700 dark:text-emerald-400"
        : "bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400"
    }`}>
      {isSuccess ? <Check className="w-4 h-4 flex-shrink-0" /> : <AlertCircle className="w-4 h-4 flex-shrink-0" />}
      {statusMsg.text}
      <button onClick={onDismiss} className="ml-auto p-0.5 hover:opacity-70">
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}


export function TagTaxonomyPanel() {
  const [statusMsg, setStatusMsg] = useState<StatusMsg | null>(null);

  const { data: taxonomyData, isLoading } = useQuery({
    queryKey: ["taxonomy"],
    queryFn: fetchTaxonomy,
  });

  const taxonomy = taxonomyData;

  const {
    editCategories,
    setEditCategories,
    newTagInputs,
    setNewTagInputs,
    newCategoryName,
    setNewCategoryName,
    startEditing,
    removeTag,
    addTag,
    addCategory,
    removeCategory,
  } = useTaxonomyEditing(taxonomy?.categories ?? {});

  const { discoverMutation, saveMutation, applyMutation } = useTaxonomyMutations(
    setEditCategories,
    setStatusMsg
  );

  const categories = resolveCategories(editCategories, taxonomy);
  const isEditing = editCategories !== null;
  const totalTags = Object.values(categories).reduce((sum, tags) => sum + tags.length, 0);
  const hasTaxonomy = taxonomy != null && Object.keys(taxonomy.categories).length > 0;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-stone-400 dark:text-stone-500" />
      </div>
    );
  }

  const isDiscovering = discoverMutation.isPending;

  const onDiscover = () => {
    setStatusMsg(null);
    discoverMutation.mutate();
  };

  const subtitleText = getPanelSubtitle(hasTaxonomy, isDiscovering, totalTags, Object.keys(categories).length);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100 flex items-center gap-2">
            <Tag className="w-4 h-4 text-teal-600 dark:text-teal-400" />
            AI Tag Taxonomy
          </h3>
          <p className="text-xs text-stone-500 dark:text-stone-400 mt-1">{subtitleText}</p>
        </div>
        <div className="flex items-center gap-2">
          {hasTaxonomy && taxonomy.status === "approved" && !isDiscovering && (
            <>
              <button
                onClick={onDiscover}
                disabled={isDiscovering}
                className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors disabled:opacity-50"
              >
                <RotateCcw className="w-4 h-4" />
                Re-discover
              </button>
              <button
                onClick={() => {
                  setStatusMsg(null);
                  applyMutation.mutate();
                }}
                disabled={applyMutation.isPending}
                className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors disabled:opacity-50"
              >
                <Wand2 className={`w-4 h-4 ${applyMutation.isPending ? "animate-spin" : ""}`} />
                {applyMutation.isPending ? "Applying..." : "Apply to All Contacts"}
              </button>
            </>
          )}
        </div>
      </div>

      {statusMsg && <StatusBanner statusMsg={statusMsg} onDismiss={() => setStatusMsg(null)} />}

      {isDiscovering && (
        <div className="bg-white dark:bg-stone-900 rounded-xl border border-teal-200 dark:border-teal-800 p-12 text-center shadow-sm">
          <div className="relative w-16 h-16 mx-auto mb-4">
            <div className="absolute inset-0 rounded-full border-4 border-teal-100 dark:border-teal-900" />
            <div className="absolute inset-0 rounded-full border-4 border-teal-500 border-t-transparent animate-spin" />
            <Wand2 className="absolute inset-0 m-auto w-6 h-6 text-teal-600 dark:text-teal-400" />
          </div>
          <h2 className="text-lg font-display font-semibold text-stone-900 dark:text-stone-100 mb-1">
            Analyzing your contacts...
          </h2>
          <p className="text-sm text-stone-500 dark:text-stone-400">
            AI is scanning contact profiles, bios, and interaction history to discover common themes and propose tags.
          </p>
          <ElapsedTimer running={true} />
        </div>
      )}

      {!hasTaxonomy && !isDiscovering && (
        <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-12 text-center">
          <div className="w-16 h-16 rounded-full bg-teal-50 dark:bg-teal-950 flex items-center justify-center mx-auto mb-4">
            <Wand2 className="w-8 h-8 text-teal-500 dark:text-teal-400" />
          </div>
          <h2 className="text-lg font-display font-semibold text-stone-900 dark:text-stone-100 mb-2">
            Discover Tags with AI
          </h2>
          <p className="text-sm text-stone-500 dark:text-stone-400 max-w-md mx-auto mb-6">
            AI will analyze all your contacts — their titles, companies, bios, and interactions — to propose a categorized tag vocabulary.
          </p>
          <button
            onClick={onDiscover}
            className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors"
          >
            <Wand2 className="w-4 h-4" />
            Discover Tags
          </button>
        </div>
      )}

      {hasTaxonomy && !isDiscovering && (
        <TaxonomyDisplay
          taxonomyStatus={taxonomy.status}
          categories={categories}
          isEditing={isEditing}
          editCategories={editCategories}
          newTagInputs={newTagInputs}
          newCategoryName={newCategoryName}
          isDiscovering={isDiscovering}
          isSavePending={saveMutation.isPending}
          onSetNewTagInputs={setNewTagInputs}
          onSetNewCategoryName={setNewCategoryName}
          onSetEditCategories={setEditCategories}
          onStartEditing={startEditing}
          onAddTag={addTag}
          onRemoveTag={removeTag}
          onRemoveCategory={removeCategory}
          onAddCategory={addCategory}
          onDiscover={onDiscover}
          onSave={(arg) => saveMutation.mutate(arg)}
        />
      )}
    </div>
  );
}
