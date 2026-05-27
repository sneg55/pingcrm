"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { client } from "@/lib/api-client";
import { extractErrorMessage } from "@/lib/api-errors";

type TaxonomyResult = {
  categories: Record<string, string[]>;
  total_tags: number;
  status: "draft" | "approved";
};

function narrowTaxonomy(
  raw: { categories: Record<string, string[]>; total_tags: number; status: string } | null | undefined
): TaxonomyResult | null {
  if (!raw) return null;
  return {
    categories: raw.categories,
    total_tags: raw.total_tags,
    status: raw.status === "approved" ? "approved" : "draft",
  };
}

export type StatusMsg = { type: "success" | "error"; text: string };

export function useTaxonomyMutations(
  setEditCategories: (cats: Record<string, string[]> | null) => void,
  setStatusMsg: (msg: StatusMsg | null) => void
) {
  const queryClient = useQueryClient();

  const showStatus = (type: "success" | "error", text: string, duration = 6000) => {
    setStatusMsg({ type, text });
    if (duration > 0) setTimeout(() => setStatusMsg(null), duration);
  };

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
      showStatus(
        "success",
        `Discovered ${count} tags across ${Object.keys(data.categories).length} categories`
      );
    },
    onError: (err: Error) => {
      showStatus("error", err.message, 0);
    },
  });

  const saveMutation = useMutation({
    mutationFn: async ({
      cats,
      newStatus,
    }: {
      cats: Record<string, string[]>;
      newStatus?: string;
    }) => {
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
      showStatus(
        "success",
        data.status === "approved"
          ? "Taxonomy approved! You can now apply tags to contacts."
          : "Changes saved"
      );
    },
    onError: (err: Error) => {
      showStatus("error", err.message);
    },
  });

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
        showStatus(
          "success",
          `Tagging started in background — you'll get a notification when it's done`
        );
      } else {
        showStatus("success", `Tagged ${data.tagged_count} contacts`);
      }
      void queryClient.invalidateQueries({ queryKey: ["contacts"] });
    },
    onError: (err: Error) => {
      showStatus("error", err.message);
    },
  });

  return { discoverMutation, saveMutation, applyMutation };
}

export function useTaxonomyEditing(categories: Record<string, string[]>) {
  const [editCategories, setEditCategories] = useState<Record<string, string[]> | null>(null);
  const [newTagInputs, setNewTagInputs] = useState<Record<string, string>>({});
  const [newCategoryName, setNewCategoryName] = useState("");

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

  return {
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
  };
}
