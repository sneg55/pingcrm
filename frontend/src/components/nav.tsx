"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { Archive, Bell, Building2, ChevronDown, GitMerge, LayoutDashboard, LogOut, MapPinned, Menu, Settings, Sparkles, Users, X } from "lucide-react";
import { useUnreadCount } from "@/hooks/use-notifications";
import { useTelegramSyncProgress } from "@/hooks/use-telegram-sync";
import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/theme-toggle";
import { NavSearch } from "@/components/nav-search";

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
  { href: "/map", label: "Map", icon: MapPinned },
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
  children: Array<{ href: string; label: string; icon: React.ComponentType<{ className?: string }> }>;
  pathname: string;
}) {
  const [open, setOpen] = useState(false);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const isActive = pathname === href || pathname.startsWith(`${href  }/`) || pathname === "/identity";

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
            const isActive = pathname === href || pathname.startsWith(`${href  }/`);
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
              const isActive = pathname === item.href || pathname.startsWith(`${item.href  }/`) || (item.href === "/contacts" && pathname === "/identity");
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
