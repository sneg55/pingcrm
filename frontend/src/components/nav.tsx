"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { LayoutDashboard, Users, Sparkles, GitMerge, Settings, Bell, LogOut, ChevronDown } from "lucide-react";
import { useUnreadCount } from "@/hooks/use-notifications";
import { useState, useRef, useEffect } from "react";
import { cn } from "@/lib/utils";

const navLinks = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/contacts", label: "Contacts", icon: Users },
  { href: "/suggestions", label: "Suggestions", icon: Sparkles },
  { href: "/identity", label: "Identity", icon: GitMerge },
  { href: "/settings", label: "Settings", icon: Settings },
];

function NotificationBell() {
  const { data } = useUnreadCount();
  const count = data?.data?.count ?? 0;

  return (
    <Link
      href="/notifications"
      className="relative p-2 rounded-md text-gray-500 hover:bg-gray-100 hover:text-gray-700 transition-colors"
    >
      <Bell className="w-5 h-5" />
      {count > 0 && (
        <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </Link>
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
    <nav className="sticky top-0 z-40 bg-white border-b border-gray-200">
      <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
        {/* Logo */}
        <Link
          href="/dashboard"
          className="text-lg font-bold text-blue-600 hover:text-blue-700"
        >
          Ping
        </Link>

        {/* Navigation links */}
        <div className="flex items-center gap-1">
          {navLinks.map(({ href, label, icon: Icon }) => {
            const isActive = pathname === href || pathname.startsWith(href + "/");
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors",
                  isActive
                    ? "bg-blue-50 text-blue-700"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                )}
              >
                <Icon className="w-4 h-4" />
                {label}
              </Link>
            );
          })}
        </div>

        {/* Notifications bell */}
        <NotificationBell />

        {/* User menu */}
        <div ref={menuRef} className="relative">
          {isLoading ? (
            <div className="w-24 h-7 bg-gray-100 rounded-md animate-pulse" />
          ) : user ? (
            <>
              <button
                onClick={() => setMenuOpen((v) => !v)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm text-gray-700 hover:bg-gray-100 transition-colors"
              >
                <span className="max-w-[120px] truncate">
                  {user.full_name ?? user.email}
                </span>
                <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
              </button>

              {menuOpen && (
                <div className="absolute right-0 mt-1 w-48 bg-white rounded-lg border border-gray-200 shadow-md py-1 z-50">
                  <div className="px-3 py-2 border-b border-gray-100">
                    <p className="text-xs font-medium text-gray-900 truncate">
                      {user.full_name ?? ""}
                    </p>
                    <p className="text-xs text-gray-400 truncate">{user.email}</p>
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
              className="px-3 py-1.5 rounded-md text-sm font-medium text-blue-600 hover:bg-blue-50 transition-colors"
            >
              Sign in
            </Link>
          )}
        </div>
      </div>
    </nav>
  );
}
