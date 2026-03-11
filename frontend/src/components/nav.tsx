"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { LayoutDashboard, Users, Building2, Sparkles, GitMerge, Settings, Bell, LogOut, ChevronDown, Archive, Search } from "lucide-react";
import { useUnreadCount } from "@/hooks/use-notifications";
import { useContacts } from "@/hooks/use-contacts";
import { useState, useRef, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";

const navLinks = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
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
  { href: "/suggestions", label: "Suggestions", icon: Sparkles },
  { href: "/settings", label: "Settings", icon: Settings },
];

function NotificationBell() {
  const { data } = useUnreadCount();
  const count = data?.data?.count ?? 0;

  return (
    <Link
      href="/notifications"
      className="relative p-2 rounded-md text-stone-500 hover:bg-stone-100 hover:text-stone-700 transition-colors"
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
          isActive ? "text-teal-700" : "text-stone-600 hover:bg-stone-100 hover:text-stone-900",
        )}
      >
        <Icon className="w-4 h-4" />
        {label}
        <ChevronDown className="w-3 h-3 text-stone-400" />
        {isActive && (
          <span className="absolute bottom-[-9px] left-2 right-2 h-[2px] bg-teal-600 rounded-full" />
        )}
      </Link>
      {open && (
        <div className="absolute top-full left-0 mt-1 w-48 bg-white rounded-lg border border-stone-200 shadow-md py-1 z-50">
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
                    ? "text-teal-700 bg-teal-50"
                    : "text-stone-600 hover:bg-stone-50 hover:text-stone-900",
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
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const { data } = useContacts({
    search: query || undefined,
    page_size: 6,
  });
  const results = query.length >= 2 ? (data?.data ?? []) : [];

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
      }
    };
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const navigate = useCallback((id: string) => {
    setOpen(false);
    setQuery("");
    router.push(`/contacts/${id}`);
  }, [router]);

  if (!open) {
    return (
      <button
        onClick={() => {
          setOpen(true);
          setTimeout(() => inputRef.current?.focus(), 0);
        }}
        className="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm text-stone-400 border border-stone-200 hover:border-stone-300 hover:text-stone-500 transition-colors"
      >
        <Search className="w-3.5 h-3.5" />
        <span className="hidden sm:inline">Search contacts</span>
        <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-mono bg-stone-100 rounded text-stone-400">
          ⌘K
        </kbd>
      </button>
    );
  }

  return (
    <div ref={dropdownRef} className="relative">
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-teal-300 bg-white ring-2 ring-teal-100">
        <Search className="w-3.5 h-3.5 text-stone-400" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && results.length > 0) {
              navigate(results[0].id);
            }
          }}
          placeholder="Search contacts..."
          className="w-40 sm:w-56 text-sm bg-transparent outline-none placeholder:text-stone-400"
        />
      </div>
      {query.length >= 2 && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-white rounded-lg border border-stone-200 shadow-lg z-50 flex flex-col">
          <div className="max-h-72 overflow-auto">
            {results.length === 0 ? (
              <p className="px-3 py-4 text-sm text-stone-400 text-center">No contacts found</p>
            ) : (
              results.map((c) => (
                <button
                  key={c.id}
                  onClick={() => navigate(c.id)}
                  className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-stone-50 transition-colors"
                >
                  <div className="w-8 h-8 rounded-full bg-teal-100 text-teal-700 flex items-center justify-center text-xs font-medium shrink-0">
                    {(c.full_name || c.emails?.[0] || "?")[0].toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-stone-900 truncate">
                      {c.full_name || c.emails?.[0] || "Unnamed"}
                    </p>
                    {c.company && (
                      <p className="text-xs text-stone-400 truncate">{c.company}</p>
                    )}
                  </div>
                </button>
              ))
            )}
          </div>
          {query && (
            <button
              onClick={() => {
                setOpen(false);
                setQuery("");
                router.push(`/contacts?q=${encodeURIComponent(query)}`);
              }}
              className="shrink-0 w-full px-3 py-2 text-xs text-teal-600 hover:bg-teal-50 border-t border-stone-100 transition-colors rounded-b-lg"
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

  // Hide nav on auth and onboarding pages
  const isPublicPage =
    pathname.startsWith("/auth") || pathname.startsWith("/onboarding");
  if (isPublicPage) return null;

  return (
    <nav className="sticky top-0 z-40 bg-white border-b border-stone-200">
      <div className="max-w-6xl mx-auto px-4 h-14 flex items-center gap-6">
        {/* Logo */}
        <Link
          href="/dashboard"
          className="flex items-center gap-2 text-lg font-display font-bold text-teal-600 hover:text-teal-700 transition-colors shrink-0"
        >
          <span className="w-2.5 h-2.5 rounded-full bg-teal-500" />
          Ping
        </Link>

        {/* Search — left, right after logo */}
        <NavSearch />

        {/* Spacer */}
        <div className="flex-1" />

        {/* Navigation links */}
        <div className="flex items-center gap-0.5">
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
                    ? "text-teal-700"
                    : "text-stone-600 hover:bg-stone-100 hover:text-stone-900"
                )}
              >
                <Icon className="w-4 h-4" />
                {label}
                {isActive && (
                  <span className="absolute bottom-[-9px] left-2 right-2 h-[2px] bg-teal-600 rounded-full" />
                )}
              </Link>
            );
          })}
        </div>

        {/* Right: bell + user */}
        <div className="flex items-center gap-1.5">
          <NotificationBell />

          {/* User menu */}
          <div ref={menuRef} className="relative">
            {isLoading ? (
              <div className="w-24 h-7 bg-stone-100 rounded-md animate-pulse" />
            ) : user ? (
              <>
                <button
                  onClick={() => setMenuOpen((v) => !v)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm text-stone-700 hover:bg-stone-100 transition-colors"
                >
                  <span className="max-w-[120px] truncate">
                    {user.full_name ?? user.email}
                  </span>
                  <ChevronDown className="w-3.5 h-3.5 text-stone-400" />
                </button>

                {menuOpen && (
                  <div className="absolute right-0 mt-1 w-48 bg-white rounded-lg border border-stone-200 shadow-md py-1 z-50">
                    <div className="px-3 py-2 border-b border-stone-100">
                      <p className="text-xs font-medium text-stone-900 truncate">
                        {user.full_name ?? ""}
                      </p>
                      <p className="text-xs text-stone-400 truncate">{user.email}</p>
                    </div>
                    <button
                      onClick={() => {
                        setMenuOpen(false);
                        logout();
                      }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50 transition-colors"
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
                className="px-3 py-1.5 rounded-md text-sm font-medium text-teal-600 hover:bg-teal-50 transition-colors"
              >
                Sign in
              </Link>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}
