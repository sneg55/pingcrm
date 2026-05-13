"use client";

import { useRouter } from "next/navigation";
import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Building2, Search } from "lucide-react";

import { useContacts } from "@/hooks/use-contacts";
import { client } from "@/lib/api-client";
import { cn } from "@/lib/utils";

type SearchResult =
  | { type: "contact"; id: string; name: string; subtitle: string | null; avatarInitial: string }
  | { type: "org"; id: string; name: string; subtitle: string };

export function NavSearch() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const trimmedQuery = query.trim();
  const [tab, setTab] = useState<"all" | "contacts" | "companies">("all");
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const { data } = useContacts({
    search: tab === "companies" ? undefined : (trimmedQuery || undefined),
    page_size: tab === "all" ? 4 : 6,
  });
  const results = trimmedQuery.length >= 2 ? (data?.data ?? []) : [];

  const orgQuery = useQuery({
    queryKey: ["organizations", "nav-search", trimmedQuery, tab],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/organizations", {
        params: { query: { search: trimmedQuery, page_size: tab === "all" ? 4 : 6 } },
      });
      return (data?.data ?? []) as Array<{ id: string; name: string; contact_count: number }>;
    },
    enabled: trimmedQuery.length >= 2 && tab !== "contacts",
  });
  const orgResults = trimmedQuery.length >= 2 ? (orgQuery.data ?? []) : [];

  const combinedResults = useMemo<SearchResult[]>(() => {
    if (tab === "contacts") {
      return results.map((c) => ({
        type: "contact" as const,
        id: c.id,
        name: c.full_name || c.emails?.[0] || "Unnamed",
        subtitle: c.company || null,
        avatarInitial: (c.full_name || c.emails?.[0] || "?")[0].toUpperCase(),
      }));
    }
    if (tab === "companies") {
      return orgResults.map((o) => ({
        type: "org" as const,
        id: o.id,
        name: o.name,
        subtitle: `${o.contact_count} contact${o.contact_count !== 1 ? "s" : ""}`,
      }));
    }
    const merged: SearchResult[] = [];
    const contacts = results.map((c) => ({
      type: "contact" as const,
      id: c.id,
      name: c.full_name || c.emails?.[0] || "Unnamed",
      subtitle: c.company || null,
      avatarInitial: (c.full_name || c.emails?.[0] || "?")[0].toUpperCase(),
    }));
    const orgs = orgResults.map((o) => ({
      type: "org" as const,
      id: o.id,
      name: o.name,
      subtitle: `${o.contact_count} contact${o.contact_count !== 1 ? "s" : ""}`,
    }));
    const maxLen = Math.max(contacts.length, orgs.length);
    for (let i = 0; i < maxLen && merged.length < 6; i++) {
      if (i < contacts.length) merged.push(contacts[i]);
      if (i < orgs.length && merged.length < 6) merged.push(orgs[i]);
    }
    return merged;
  }, [tab, results, orgResults]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen(true);
        setTimeout(() => inputRef.current?.focus(), 0);
      }
      if (e.key === "Escape") {
        setOpen(false);
        setQuery("");
        setTab("all");
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery("");
        setTab("all");
      }
    };
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const navigate = useCallback((path: string) => {
    setOpen(false);
    setQuery("");
    setTab("all");
    router.push(path);
  }, [router]);

  if (!open) {
    return (
      <button
        onClick={() => {
          setOpen(true);
          setTimeout(() => inputRef.current?.focus(), 0);
        }}
        className="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm text-stone-400 border border-stone-200 hover:border-stone-300 hover:text-stone-500 dark:text-stone-500 dark:border-stone-700 dark:hover:border-stone-600 dark:hover:text-stone-400 transition-colors whitespace-nowrap"
      >
        <Search className="w-3.5 h-3.5 shrink-0" />
        <span className="hidden sm:inline">Search</span>
        <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-mono bg-stone-100 dark:bg-stone-800 rounded text-stone-400 dark:text-stone-500">
          ⌘K
        </kbd>
      </button>
    );
  }

  return (
    <div ref={dropdownRef} className="relative">
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-teal-300 bg-white dark:bg-stone-900 dark:border-teal-700 ring-2 ring-teal-100 dark:ring-teal-900">
        <Search className="w-3.5 h-3.5 text-stone-400 dark:text-stone-500" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
              setQuery(e.target.value);
              if (e.target.value.trim().length < 2) setTab("all");
            }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && combinedResults.length > 0) {
              const first = combinedResults[0];
              navigate(first.type === "contact" ? `/contacts/${first.id}` : `/organizations/${first.id}`);
            }
          }}
          placeholder="Search..."
          className="w-40 sm:w-56 text-sm bg-transparent outline-none placeholder:text-stone-400 dark:placeholder:text-stone-500 dark:text-stone-100"
        />
      </div>
      {trimmedQuery.length >= 2 && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 shadow-lg z-50 flex flex-col">
          <div className="flex items-center gap-1 px-3 pt-2 pb-1 border-b border-stone-100 dark:border-stone-800">
            {(["all", "contacts", "companies"] as const).map((t) => (
              <button
                key={t}
                aria-label={t === "all" ? "All" : t === "contacts" ? "Contacts" : "Companies"}
                onClick={() => setTab(t)}
                className={cn(
                  "px-2 py-1 text-xs font-medium rounded transition-colors",
                  tab === t
                    ? "text-teal-700 dark:text-teal-400 bg-teal-50 dark:bg-teal-950"
                    : "text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300"
                )}
              >
                {t === "all" ? "All" : t === "contacts" ? "Contacts" : "Companies"}
              </button>
            ))}
          </div>
          <div className="max-h-72 overflow-auto">
            {combinedResults.length === 0 ? (
              <p className="px-3 py-4 text-sm text-stone-400 dark:text-stone-500 text-center">
                {tab === "companies" ? "No companies found" : tab === "contacts" ? "No contacts found" : "No results found"}
              </p>
            ) : (
              combinedResults.map((r) => (
                <button
                  key={`${r.type}-${r.id}`}
                  onClick={() => navigate(r.type === "contact" ? `/contacts/${r.id}` : `/organizations/${r.id}`)}
                  className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors"
                >
                  {r.type === "contact" ? (
                    <div className="w-8 h-8 rounded-full bg-teal-100 dark:bg-teal-900 text-teal-700 dark:text-teal-300 flex items-center justify-center text-xs font-medium shrink-0">
                      {r.avatarInitial}
                    </div>
                  ) : (
                    <div className="w-8 h-8 rounded-full bg-stone-100 dark:bg-stone-800 text-stone-500 dark:text-stone-400 flex items-center justify-center shrink-0">
                      <Building2 className="w-4 h-4" />
                    </div>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-stone-900 dark:text-stone-100 truncate">
                      {r.name}
                    </p>
                    {r.subtitle && (
                      <p className="text-xs text-stone-400 dark:text-stone-500 truncate">{r.subtitle}</p>
                    )}
                  </div>
                  {tab === "all" && (
                    <span className="text-[10px] text-stone-400 dark:text-stone-500 shrink-0">
                      {r.type === "contact" ? "Contact" : "Company"}
                    </span>
                  )}
                </button>
              ))
            )}
          </div>
          {trimmedQuery && (
            <button
              onClick={() => {
                const dest = tab === "companies"
                  ? `/organizations?q=${encodeURIComponent(trimmedQuery)}`
                  : `/contacts?q=${encodeURIComponent(trimmedQuery)}`;
                navigate(dest);
              }}
              className="shrink-0 w-full px-3 py-2 text-xs text-teal-600 dark:text-teal-400 hover:bg-teal-50 dark:hover:bg-teal-950 border-t border-stone-100 dark:border-stone-800 transition-colors rounded-b-lg"
            >
              View all results for &ldquo;{trimmedQuery}&rdquo;
            </button>
          )}
        </div>
      )}
    </div>
  );
}
