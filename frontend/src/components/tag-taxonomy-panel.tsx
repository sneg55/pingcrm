"use client";

import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Tag, Plus, X, Loader2, Wand2, Check, RotateCcw, AlertCircle } from "lucide-react";
import { client } from "@/lib/api-client";

interface TaxonomyResult {
  categories: Record<string, string[]>;
  total_tags: number;
  status: "draft" | "approved";
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
    <span className="text-xs text-stone-400 mt-2 block">
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
      const { data, error } = await client.GET("/api/v1/contacts/tags/taxonomy" as any);
      if (error) return null;
      return (data as any)?.data as TaxonomyResult | null;
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
      const { data, error, response } = await client.POST("/api/v1/contacts/tags/discover" as any);
      if (error || !response.ok) {
        throw new Error((error as any)?.detail || "Discovery failed");
      }
      return (data as any)?.data as TaxonomyResult;
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
      const { data, error, response } = await client.PUT("/api/v1/contacts/tags/taxonomy" as any, {
        body: { categories: cats, status: newStatus },
      });
      if (error || !response.ok) {
        throw new Error((error as any)?.detail || "Save failed");
      }
      return (data as any)?.data as TaxonomyResult;
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
      const { data, error, response } = await client.POST("/api/v1/contacts/tags/apply" as any, {
        body: {},
      });
      if (error || !response.ok) {
        throw new Error((error as any)?.detail || "Apply failed");
      }
      const json = await res.json();
      return json.data as { tagged_count: number; task_id: string | null };
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
        <Loader2 className="w-6 h-6 animate-spin text-stone-400" />
      </div>
    );
  }

  const isDiscovering = discoverMutation.isPending;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-sm font-semibold text-stone-900 flex items-center gap-2">
            <Tag className="w-4 h-4 text-teal-600" />
            AI Tag Taxonomy
          </h3>
          <p className="text-xs text-stone-500 mt-1">
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
                className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-stone-200 text-stone-600 hover:bg-stone-100 transition-colors disabled:opacity-50"
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
            ? "bg-green-50 border border-green-200 text-green-700"
            : "bg-red-50 border border-red-200 text-red-700"
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
        <div className="bg-white rounded-xl border border-teal-200 p-12 text-center shadow-sm">
          <div className="relative w-16 h-16 mx-auto mb-4">
            <div className="absolute inset-0 rounded-full border-4 border-teal-100" />
            <div className="absolute inset-0 rounded-full border-4 border-teal-500 border-t-transparent animate-spin" />
            <Wand2 className="absolute inset-0 m-auto w-6 h-6 text-teal-600" />
          </div>
          <h2 className="text-lg font-display font-semibold text-stone-900 mb-1">
            Analyzing your contacts...
          </h2>
          <p className="text-sm text-stone-500">
            AI is scanning contact profiles, bios, and interaction history to discover common themes and propose tags.
          </p>
          <ElapsedTimer running={true} />
        </div>
      )}

      {/* Empty state */}
      {!hasTaxonomy && !isDiscovering && (
        <div className="bg-white rounded-xl border border-stone-200 p-12 text-center">
          <div className="w-16 h-16 rounded-full bg-teal-50 flex items-center justify-center mx-auto mb-4">
            <Wand2 className="w-8 h-8 text-teal-500" />
          </div>
          <h2 className="text-lg font-display font-semibold text-stone-900 mb-2">
            Discover Tags with AI
          </h2>
          <p className="text-sm text-stone-500 max-w-md mx-auto mb-6">
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
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-amber-800">Draft Taxonomy</p>
                <p className="text-xs text-amber-600 mt-0.5">
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
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md border border-amber-300 text-amber-700 hover:bg-amber-100 transition-colors disabled:opacity-50"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  Re-discover
                </button>
                {!isEditing && (
                  <button
                    onClick={startEditing}
                    className="px-3 py-1.5 text-sm font-medium rounded-md border border-amber-300 text-amber-700 hover:bg-amber-100 transition-colors"
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
            <div className="bg-teal-50 border border-teal-200 rounded-lg p-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Check className="w-4 h-4 text-teal-600" />
                <p className="text-sm font-medium text-teal-800">Approved Taxonomy</p>
              </div>
              <button
                onClick={startEditing}
                className="px-3 py-1.5 text-sm font-medium rounded-md border border-teal-300 text-teal-700 hover:bg-teal-100 transition-colors"
              >
                Edit
              </button>
            </div>
          )}

          {isEditing && (
            <div className="flex items-center gap-2 justify-end">
              <button
                onClick={() => setEditCategories(null)}
                className="px-3 py-1.5 text-sm rounded-md border border-stone-200 text-stone-600 hover:bg-stone-100 transition-colors"
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
              className="bg-white rounded-lg border border-stone-200 p-5"
            >
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-stone-700">{category}</h3>
                {isEditing && (
                  <button
                    onClick={() => removeCategory(category)}
                    className="text-xs text-red-500 hover:text-red-700 transition-colors"
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
                        ? "bg-stone-100 text-stone-700 pr-1.5"
                        : "bg-teal-50 text-teal-700 border border-teal-200"
                    }`}
                  >
                    {tag}
                    {isEditing && (
                      <button
                        onClick={() => removeTag(category, tag)}
                        className="p-0.5 rounded-full hover:bg-stone-200 transition-colors"
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
                      className="w-28 px-2 py-1 text-sm rounded-md border border-stone-200 focus:outline-none focus:ring-1 focus:ring-teal-500 focus:border-teal-500"
                    />
                    <button
                      type="submit"
                      className="ml-1 p-1 rounded-md hover:bg-stone-100 text-stone-400 hover:text-teal-600 transition-colors"
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
                className="flex-1 px-3 py-2 text-sm rounded-lg border border-dashed border-stone-300 focus:outline-none focus:ring-1 focus:ring-teal-500 focus:border-teal-500"
              />
              <button
                type="submit"
                disabled={!newCategoryName.trim()}
                className="px-4 py-2 text-sm font-medium rounded-lg border border-stone-200 text-stone-600 hover:bg-stone-100 disabled:opacity-50 transition-colors"
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
