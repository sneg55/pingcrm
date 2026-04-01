"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { LayoutDashboard, Users, Building2, Sparkles, GitMerge, Settings, Bell, LogOut, ChevronDown, Archive, Search, Menu, X } from "lucide-react";
import { useUnreadCount } from "@/hooks/use-notifications";
import { useContacts } from "@/hooks/use-contacts";
import { useTelegramSyncProgress } from "@/hooks/use-telegram-sync";
import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { client } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/theme-toggle";

type SearchResult =
  | { type: "contact"; id: string; name: string; subtitle: string | null; avatarInitial: string }
  | { type: "org"; id: string; name: string; subtitle: string };

const navLinks = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/suggestions", label: "Suggestions", icon: Sparkles },
  {
    href: "/contacts",
    label: "Contacts",
    icon: Users,
    children: [
      { href: "/contacts", label: "All Contacts", icon: Users },
      { href: "/contacts/archive", label: "Archive", icon: Archive },
      { href: "/identity", label: "Resolve Duplicates", icon: GitMerge },
    ],
  },
  { href: "/organizations", label: "Orgs", icon: Building2 },
  { href: "/settings", label: "Settings", icon: Settings },
];

function LogoDot() {
  const { data } = useTelegramSyncProgress();
  const syncing = !!data?.active;

  if (syncing) {
    return (
      <span
        title="Telegram sync in progress"
        className="relative flex items-center justify-center w-2.5 h-2.5"
        aria-label="Telegram sync in progress"
      >
        <span className="absolute inline-flex w-full h-full rounded-full bg-sky-400 opacity-75 animate-ping" />
        <span className="relative inline-flex w-2 h-2 rounded-full bg-sky-500" />
      </span>
    );
  }

  return <span className="w-2.5 h-2.5 rounded-full bg-teal-500" />;
}

function NotificationBell() {
  const { data } = useUnreadCount();
  const count = data?.data?.count ?? 0;

  return (
    <Link
      href="/notifications"
      className="relative p-2 rounded-md text-stone-500 hover:bg-stone-100 hover:text-stone-700 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-200 transition-colors"
    >
      <Bell className="w-5 h-5" />
      {count > 0 && (
        <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold animate-pulse">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </Link>
  );
}

function NavDropdown({
  href,
  label,
  icon: Icon,
  children,
  pathname,
}: {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  children: { href: string; label: string; icon: React.ComponentType<{ className?: string }> }[];
  pathname: string;
}) {
  const [open, setOpen] = useState(false);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isActive = pathname === href || pathname.startsWith(href + "/") || pathname === "/identity";

  const handleEnter = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setOpen(true);
  };
  const handleLeave = () => {
    timeoutRef.current = setTimeout(() => setOpen(false), 150);
  };

  return (
    <div className="relative" onMouseEnter={handleEnter} onMouseLeave={handleLeave}>
      <Link
        href={href}
        className={cn(
          "relative flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
          isActive
            ? "text-teal-700 dark:text-teal-400"
            : "text-stone-600 hover:bg-stone-100 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-100",
        )}
      >
        <Icon className="w-4 h-4" />
        {label}
        <ChevronDown className="w-3 h-3 text-stone-400 dark:text-stone-500" />
        {isActive && (
          <span className="absolute bottom-[-9px] left-2 right-2 h-[2px] bg-teal-600 dark:bg-teal-400 rounded-full" />
        )}
      </Link>
      {open && (
        <div className="absolute top-full left-0 mt-1 w-48 bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 shadow-md py-1 z-50">
          {children.map((child) => {
            const ChildIcon = child.icon;
            const childActive = pathname === child.href || (child.href === "/identity" && pathname.startsWith("/identity"));
            return (
              <Link
                key={child.href}
                href={child.href}
                onClick={() => setOpen(false)}
                className={cn(
                  "flex items-center gap-2 px-3 py-2 text-sm transition-colors",
                  childActive
                    ? "text-teal-700 bg-teal-50 dark:text-teal-400 dark:bg-teal-950"
                    : "text-stone-600 hover:bg-stone-50 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-100",
                )}
              >
                <ChildIcon className="w-4 h-4" />
                {child.label}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

function NavSearch() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<"all" | "contacts" | "companies">("all");
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const { data } = useContacts({
    search: tab === "companies" ? undefined : (query || undefined),
    page_size: tab === "all" ? 4 : 6,
  });
  const results = query.length >= 2 ? (data?.data ?? []) : [];

  const orgQuery = useQuery({
    queryKey: ["organizations", "nav-search", query, tab],
    queryFn: async () => {
      const { data } = await client.GET("/api/v1/organizations", {
        params: { query: { search: query, page_size: tab === "all" ? 4 : 6 } },
      });
      return (data?.data ?? []) as Array<{ id: string; name: string; contact_count: number }>;
    },
    enabled: query.length >= 2 && tab !== "contacts",
  });
  const orgResults = query.length >= 2 ? (orgQuery.data ?? []) : [];

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
    // "all" tab: interleave contacts and orgs
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

  // Cmd+K / Ctrl+K shortcut
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

  // Close on outside click
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
              if (e.target.value.length < 2) setTab("all");
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
      {query.length >= 2 && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 shadow-lg z-50 flex flex-col">
          {/* Tab bar */}
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
          {query && (
            <button
              onClick={() => {
                const dest = tab === "companies"
                  ? `/organizations?q=${encodeURIComponent(query)}`
                  : `/contacts?q=${encodeURIComponent(query)}`;
                navigate(dest);
              }}
              className="shrink-0 w-full px-3 py-2 text-xs text-teal-600 dark:text-teal-400 hover:bg-teal-50 dark:hover:bg-teal-950 border-t border-stone-100 dark:border-stone-800 transition-colors rounded-b-lg"
            >
              View all results for &ldquo;{query}&rdquo;
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export function Nav() {
  const pathname = usePathname();
  const { user, isLoading, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  useEffect(() => {
    setMobileMenuOpen(false);
  }, [pathname]);

  // Hide nav on auth pages
  const isPublicPage = pathname.startsWith("/auth");
  if (isPublicPage) return null;

  return (
    <nav className="sticky top-0 z-40 bg-white dark:bg-stone-900 border-b border-stone-200 dark:border-stone-800">
      <div className="max-w-6xl mx-auto px-4 h-14 flex items-center gap-6">
        {/* Logo */}
        <div className="shrink-0">
          <Link
            href="/dashboard"
            className="flex items-center gap-2 text-lg font-display font-bold text-teal-600 dark:text-teal-400 hover:text-teal-700 dark:hover:text-teal-300 transition-colors"
          >
            <LogoDot />
            Ping
          </Link>
        </div>

        {/* Search — left, right after logo */}
        <NavSearch />

        {/* Hamburger button — mobile only */}
        <button
          onClick={() => setMobileMenuOpen(v => !v)}
          className="md:hidden p-2 rounded-md text-stone-500 hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800 transition-colors"
          aria-label="Toggle menu"
          aria-expanded={mobileMenuOpen}
          aria-controls="mobile-nav-menu"
        >
          {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Navigation links — desktop only */}
        <div className="hidden md:flex items-center gap-0.5">
          {navLinks.map((item) => {
            if ("children" in item && item.children) {
              return (
                <NavDropdown
                  key={item.href}
                  href={item.href}
                  label={item.label}
                  icon={item.icon}
                  children={item.children}
                  pathname={pathname}
                />
              );
            }
            const { href, label, icon: Icon } = item;
            const isActive = pathname === href || pathname.startsWith(href + "/");
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "relative flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
                  isActive
                    ? "text-teal-700 dark:text-teal-400"
                    : "text-stone-600 hover:bg-stone-100 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-100"
                )}
              >
                <Icon className="w-4 h-4" />
                {label}
                {isActive && (
                  <span className="absolute bottom-[-9px] left-2 right-2 h-[2px] bg-teal-600 dark:bg-teal-400 rounded-full" />
                )}
              </Link>
            );
          })}
        </div>

        {/* Right: theme toggle + bell + user */}
        <div className="flex items-center gap-1.5">
          <ThemeToggle />
          <NotificationBell />

          {/* User menu */}
          <div ref={menuRef} className="relative">
            {isLoading ? (
              <div className="w-24 h-7 bg-stone-100 dark:bg-stone-800 rounded-md animate-pulse" />
            ) : user ? (
              <>
                <button
                  onClick={() => setMenuOpen((v) => !v)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm text-stone-700 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                >
                  <span className="hidden sm:inline max-w-[120px] truncate">
                    {user.full_name ?? user.email}
                  </span>
                  <ChevronDown className="hidden sm:block w-3.5 h-3.5 text-stone-400 dark:text-stone-500" />
                </button>

                {menuOpen && (
                  <div className="menu-enter absolute right-0 mt-1 w-48 bg-white dark:bg-stone-900 rounded-lg border border-stone-200 dark:border-stone-700 shadow-md py-1 z-50">
                    <div className="px-3 py-2 border-b border-stone-100 dark:border-stone-800">
                      <p className="text-xs font-medium text-stone-900 dark:text-stone-100 truncate">
                        {user.full_name ?? ""}
                      </p>
                      <p className="text-xs text-stone-400 dark:text-stone-500 truncate">{user.email}</p>
                    </div>
                    <button
                      onClick={() => {
                        setMenuOpen(false);
                        logout();
                      }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950 transition-colors"
                    >
                      <LogOut className="w-4 h-4" />
                      Sign out
                    </button>
                  </div>
                )}
              </>
            ) : (
              <Link
                href="/auth/login"
                className="px-3 py-1.5 rounded-md text-sm font-medium text-teal-600 dark:text-teal-400 hover:bg-teal-50 dark:hover:bg-teal-950 transition-colors"
              >
                Sign in
              </Link>
            )}
          </div>
        </div>
      </div>

      {/* Mobile menu panel */}
      {mobileMenuOpen && (
        <div id="mobile-nav-menu" className="md:hidden border-t border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900">
          <div className="max-w-6xl mx-auto px-4 py-3 space-y-1">
            {navLinks.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href || pathname.startsWith(item.href + "/") || (item.href === "/contacts" && pathname === "/identity");
              return (
                <div key={item.href}>
                  <Link
                    href={item.href}
                    className={cn(
                      "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
                      isActive
                        ? "bg-teal-50 dark:bg-teal-950 text-teal-700 dark:text-teal-400"
                        : "text-stone-600 dark:text-stone-400 hover:bg-stone-50 dark:hover:bg-stone-800"
                    )}
                  >
                    <Icon className="w-5 h-5" />
                    {item.label}
                  </Link>
                  {"children" in item && item.children && (
                    <div className="ml-8 mt-1 space-y-1">
                      {item.children.map((child) => {
                        const ChildIcon = child.icon;
                        const childActive = pathname === child.href;
                        return (
                          <Link
                            key={child.href}
                            href={child.href}
                            className={cn(
                              "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors",
                              childActive
                                ? "text-teal-700 dark:text-teal-400 bg-teal-50/50 dark:bg-teal-950/50"
                                : "text-stone-500 dark:text-stone-500 hover:text-stone-700 dark:hover:text-stone-300"
                            )}
                          >
                            <ChildIcon className="w-4 h-4" />
                            {child.label}
                          </Link>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </nav>
  );
}
