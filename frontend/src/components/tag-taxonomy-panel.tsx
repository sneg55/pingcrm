"use client";

import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Tag, Plus, X, Loader2, Wand2, Check, RotateCcw, AlertCircle } from "lucide-react";
import { client } from "@/lib/api-client";
import { extractErrorMessage } from "@/lib/api-errors";

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


export function TagTaxonomyPanel() {
  const queryClient = useQueryClient();
  const [editCategories, setEditCategories] = useState<Record<string, string[]> | null>(null);
  const [newTagInputs, setNewTagInputs] = useState<Record<string, string>>({});
  const [newCategoryName, setNewCategoryName] = useState("");
  const [statusMsg, setStatusMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const showStatus = (type: "success" | "error", text: string, duration = 6000) => {
    setStatusMsg({ type, text });
    if (duration > 0) setTimeout(() => setStatusMsg(null), duration);
  };

  // Fetch taxonomy
  const { data: taxonomyData, isLoading } = useQuery({
    queryKey: ["taxonomy"],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/contacts/tags/taxonomy", {});
      if (error) return null;
      return narrowTaxonomy(data?.data);
    },
  });

  const taxonomy = taxonomyData;
  const categories = editCategories ?? taxonomy?.categories ?? {};
  const isEditing = editCategories !== null;
  const totalTags = Object.values(categories).reduce((sum, tags) => sum + tags.length, 0);
  const hasTaxonomy = taxonomy && Object.keys(taxonomy.categories).length > 0;

  // Discover mutation
  const discoverMutation = useMutation({
    mutationFn: async () => {
      const { data, error, response } = await client.POST("/api/v1/contacts/tags/discover", {});
      if (error || !response.ok) {
        throw new Error(extractErrorMessage(error) ?? "Discovery failed");
      }
      const narrowed = narrowTaxonomy(data?.data);
      if (!narrowed) throw new Error("Discovery returned no taxonomy");
      return narrowed;
    },
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["taxonomy"] });
      setEditCategories(data.categories);
      const count = Object.values(data.categories).reduce((s, t) => s + t.length, 0);
      showStatus("success", `Discovered ${count} tags across ${Object.keys(data.categories).length} categories`);
    },
    onError: (err: Error) => {
      showStatus("error", err.message, 0);
    },
  });

  // Save/approve taxonomy
  const saveMutation = useMutation({
    mutationFn: async ({ cats, newStatus }: { cats: Record<string, string[]>; newStatus?: string }) => {
      const { data, error, response } = await client.PUT("/api/v1/contacts/tags/taxonomy", {
        body: { categories: cats, status: newStatus },
      });
      if (error || !response.ok) {
        throw new Error(extractErrorMessage(error) ?? "Save failed");
      }
      const narrowed = narrowTaxonomy(data?.data);
      if (!narrowed) throw new Error("Save returned no taxonomy");
      return narrowed;
    },
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["taxonomy"] });
      setEditCategories(null);
      showStatus("success", data.status === "approved" ? "Taxonomy approved! You can now apply tags to contacts." : "Changes saved");
    },
    onError: (err: Error) => {
      showStatus("error", err.message);
    },
  });

  // Apply tags mutation
  const applyMutation = useMutation({
    mutationFn: async () => {
      const { data, error, response } = await client.POST("/api/v1/contacts/tags/apply", {
        body: {},
      });
      if (error || !response.ok) {
        throw new Error(extractErrorMessage(error) ?? "Apply failed");
      }
      const result = data?.data;
      if (!result) throw new Error("Apply returned no result");
      return result;
    },
    onSuccess: (data) => {
      if (data.task_id) {
        showStatus("success", `Tagging started in background — you'll get a notification when it's done`);
      } else {
        showStatus("success", `Tagged ${data.tagged_count} contacts`);
      }
      void queryClient.invalidateQueries({ queryKey: ["contacts"] });
    },
    onError: (err: Error) => {
      showStatus("error", err.message);
    },
  });

  const startEditing = () => {
    setEditCategories({ ...categories });
  };

  const removeTag = (category: string, tag: string) => {
    if (!editCategories) return;
    const updated = { ...editCategories };
    updated[category] = updated[category].filter((t) => t !== tag);
    if (updated[category].length === 0) {
      delete updated[category];
    }
    setEditCategories(updated);
  };

  const addTag = (category: string) => {
    const tag = (newTagInputs[category] || "").trim();
    if (!tag || !editCategories) return;
    const updated = { ...editCategories };
    if (!updated[category]) updated[category] = [];
    if (!updated[category].some((t) => t.toLowerCase() === tag.toLowerCase())) {
      updated[category] = [...updated[category], tag];
    }
    setEditCategories(updated);
    setNewTagInputs({ ...newTagInputs, [category]: "" });
  };

  const addCategory = () => {
    const name = newCategoryName.trim();
    if (!name || !editCategories || editCategories[name]) return;
    setEditCategories({ ...editCategories, [name]: [] });
    setNewCategoryName("");
  };

  const removeCategory = (category: string) => {
    if (!editCategories) return;
    const updated = { ...editCategories };
    delete updated[category];
    setEditCategories(updated);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-stone-400 dark:text-stone-500" />
      </div>
    );
  }

  const isDiscovering = discoverMutation.isPending;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100 flex items-center gap-2">
            <Tag className="w-4 h-4 text-teal-600 dark:text-teal-400" />
            AI Tag Taxonomy
          </h3>
          <p className="text-xs text-stone-500 dark:text-stone-400 mt-1">
            {hasTaxonomy && !isDiscovering
              ? `${totalTags} tags across ${Object.keys(categories).length} categories`
              : isDiscovering
                ? "Scanning contacts..."
                : "Discover tags from your contacts using AI"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {hasTaxonomy && taxonomy.status === "approved" && !isDiscovering && (
            <>
              <button
                onClick={() => {
                  setStatusMsg(null);
                  discoverMutation.mutate();
                }}
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

      {/* Status messages */}
      {statusMsg && (
        <div className={`mb-4 px-4 py-3 rounded-lg text-sm flex items-center gap-2 ${
          statusMsg.type === "success"
            ? "bg-green-50 dark:bg-emerald-950 border border-green-200 dark:border-emerald-800 text-green-700 dark:text-emerald-400"
            : "bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-400"
        }`}>
          {statusMsg.type === "success" ? <Check className="w-4 h-4 flex-shrink-0" /> : <AlertCircle className="w-4 h-4 flex-shrink-0" />}
          {statusMsg.text}
          <button onClick={() => setStatusMsg(null)} className="ml-auto p-0.5 hover:opacity-70">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Discovery in progress */}
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

      {/* Empty state */}
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
            onClick={() => {
              setStatusMsg(null);
              discoverMutation.mutate();
            }}
            className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors"
          >
            <Wand2 className="w-4 h-4" />
            Discover Tags
          </button>
        </div>
      )}

      {/* Taxonomy display */}
      {hasTaxonomy && !isDiscovering && (
        <div className="space-y-4">
          {taxonomy.status === "draft" && (
            <div className="bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-lg p-4 flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-amber-800 dark:text-amber-400">Draft Taxonomy</p>
                <p className="text-xs text-amber-600 dark:text-amber-500 mt-0.5">
                  Review and edit the proposed tags, then approve to start tagging contacts.
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    setStatusMsg(null);
                    discoverMutation.mutate();
                  }}
                  disabled={isDiscovering}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md border border-amber-300 dark:border-amber-700 text-amber-700 dark:text-amber-400 hover:bg-amber-100 dark:hover:bg-amber-900 transition-colors disabled:opacity-50"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  Re-discover
                </button>
                {!isEditing && (
                  <button
                    onClick={startEditing}
                    className="px-3 py-1.5 text-sm font-medium rounded-md border border-amber-300 dark:border-amber-700 text-amber-700 dark:text-amber-400 hover:bg-amber-100 dark:hover:bg-amber-900 transition-colors"
                  >
                    Edit
                  </button>
                )}
                <button
                  onClick={() => {
                    const cats = editCategories || taxonomy.categories;
                    saveMutation.mutate({ cats, newStatus: "approved" });
                  }}
                  disabled={saveMutation.isPending}
                  className="px-4 py-1.5 text-sm font-medium rounded-md bg-teal-600 text-white hover:bg-teal-700 disabled:opacity-50 transition-colors"
                >
                  {saveMutation.isPending ? "Saving..." : "Approve Taxonomy"}
                </button>
              </div>
            </div>
          )}

          {taxonomy.status === "approved" && !isEditing && (
            <div className="bg-teal-50 dark:bg-teal-950 border border-teal-200 dark:border-teal-800 rounded-lg p-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Check className="w-4 h-4 text-teal-600 dark:text-teal-400" />
                <p className="text-sm font-medium text-teal-800 dark:text-teal-300">Approved Taxonomy</p>
              </div>
              <button
                onClick={startEditing}
                className="px-3 py-1.5 text-sm font-medium rounded-md border border-teal-300 dark:border-teal-700 text-teal-700 dark:text-teal-400 hover:bg-teal-100 dark:hover:bg-teal-900 transition-colors"
              >
                Edit
              </button>
            </div>
          )}

          {isEditing && (
            <div className="flex items-center gap-2 justify-end">
              <button
                onClick={() => setEditCategories(null)}
                className="px-3 py-1.5 text-sm rounded-md border border-stone-200 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  if (editCategories) {
                    saveMutation.mutate({ cats: editCategories, newStatus: "approved" });
                  }
                }}
                disabled={saveMutation.isPending}
                className="px-4 py-1.5 text-sm font-medium rounded-md bg-teal-600 text-white hover:bg-teal-700 disabled:opacity-50 transition-colors"
              >
                {saveMutation.isPending ? "Saving..." : "Approve Taxonomy"}
              </button>
            </div>
          )}

          {Object.entries(categories).map(([category, tags]) => (
            <div
              key={category}
              className="bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 p-5"
            >
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-stone-700 dark:text-stone-300">{category}</h3>
                {isEditing && (
                  <button
                    onClick={() => removeCategory(category)}
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
                        onClick={() => removeTag(category, tag)}
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
                      addTag(category);
                    }}
                    className="inline-flex items-center"
                  >
                    <input
                      type="text"
                      value={newTagInputs[category] || ""}
                      onChange={(e) =>
                        setNewTagInputs({ ...newTagInputs, [category]: e.target.value })
                      }
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
          ))}

          {isEditing && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                addCategory();
              }}
              className="flex items-center gap-2"
            >
              <input
                type="text"
                value={newCategoryName}
                onChange={(e) => setNewCategoryName(e.target.value)}
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
      )}
    </div>
  );
}
