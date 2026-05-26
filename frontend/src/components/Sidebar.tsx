"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import { UserButton, useUser } from "@clerk/nextjs";
import {
  Home, BarChart2, Layers, Wrench, TrendingUp, MessageSquare,
  Lightbulb, Share2, FileText, ShieldCheck,
  ChevronLeft, ChevronRight,
} from "lucide-react";

type NavItem = { href: string; icon: React.ElementType; label: string };

const MAIN_NAV: NavItem[] = [
  { href: "/home",          icon: Home,          label: "Home" },
  { href: "/strategies",    icon: BarChart2,     label: "Strategies" },
  { href: "/builder",       icon: Layers,        label: "Builder" },
  { href: "/resources",     icon: Wrench,        label: "Resources" },
  { href: "/analytics",     icon: TrendingUp,    label: "Analytics" },
  { href: "/testimonials",  icon: MessageSquare, label: "Testimonials" },
];

const BOTTOM_NAV: NavItem[] = [
  { href: "/suggestions", icon: Lightbulb, label: "Suggestions" },
  { href: "/affiliate",   icon: Share2,    label: "Affiliate" },
  { href: "/legal",       icon: FileText,  label: "Legal" },
];

function NavLink({
  item,
  collapsed,
  active,
}: {
  item: NavItem;
  collapsed: boolean;
  active: boolean;
}) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      title={collapsed ? item.label : undefined}
      className={`flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] transition-colors
        ${active ? "bg-money/10 text-money font-medium" : "text-muted hover:text-ink hover:bg-surface2"}
        ${collapsed ? "justify-center" : ""}`}
    >
      <Icon size={15} className="shrink-0" />
      {!collapsed && <span>{item.label}</span>}
    </Link>
  );
}

export function Sidebar() {
  const pathname  = usePathname();
  const [collapsed,  setCollapsed]  = useState(false);
  const [adminUser,  setAdminUser]  = useState(false);

  useEffect(() => {
    fetch("/api/me")
      .then((r) => r.json())
      .then((d) => setAdminUser(d.isAdmin === true))
      .catch(() => {});
  }, []);

  const isActive = (href: string) =>
    href.startsWith("/") && !href.startsWith("#") &&
    (pathname === href || (href !== "/" && pathname.startsWith(href)));

  return (
    <aside
      className={`
        ${collapsed ? "w-[60px]" : "w-[228px]"}
        shrink-0 h-screen sticky top-0 flex flex-col
        bg-surface border-r border-border
        transition-[width] duration-200 overflow-hidden
      `}
    >
      {/* Logo row */}
      <div
        className={`h-14 flex items-center border-b border-border px-3 shrink-0
          ${collapsed ? "justify-center" : "justify-between"}`}
      >
        <Link href="/" className={`flex items-center gap-2 ${collapsed ? "" : ""}`}>
          <div className="w-6 h-6 rounded-md bg-ink flex items-center justify-center text-paper font-bold text-[11px] shrink-0 hover:bg-money transition-colors">
            E
          </div>
          {!collapsed && (
            <span className="font-semibold text-[14px] whitespace-nowrap">Edgekit</span>
          )}
        </Link>
        {!collapsed && (
          <button
            onClick={() => setCollapsed(true)}
            className="p-1 rounded hover:bg-surface2 text-muted hover:text-ink transition-colors"
            title="Collapse sidebar"
          >
            <ChevronLeft size={14} />
          </button>
        )}
      </div>

      {/* Main navigation */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-0.5">
        {MAIN_NAV.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            collapsed={collapsed}
            active={isActive(item.href)}
          />
        ))}
      </nav>

      {/* Divider */}
      <div className="border-t border-border mx-3" />

      {/* Bottom navigation */}
      <div className="px-2 py-2 space-y-0.5">
        {adminUser && (
          <NavLink
            item={{ href: "/admin", icon: ShieldCheck, label: "Admin" }}
            collapsed={collapsed}
            active={isActive("/admin")}
          />
        )}
        {BOTTOM_NAV.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            collapsed={collapsed}
            active={isActive(item.href)}
          />
        ))}
      </div>

      {/* Clerk user — profile dropdown + sign out */}
      <UserBar collapsed={collapsed} />

      {/* Expand button (only when collapsed) */}
      {collapsed && (
        <div className="border-t border-border p-2">
          <button
            onClick={() => setCollapsed(false)}
            className="w-full flex justify-center p-2 rounded-lg hover:bg-surface2 text-muted hover:text-ink transition-colors"
            title="Expand sidebar"
          >
            <ChevronRight size={14} />
          </button>
        </div>
      )}
    </aside>
  );
}

/**
 * Clerk-backed user row. Shows avatar + email when expanded, just avatar when
 * collapsed. The UserButton opens Clerk's account modal (profile, sign out).
 */
function UserBar({ collapsed }: { collapsed: boolean }) {
  const { user, isLoaded } = useUser();
  if (!isLoaded || !user) {
    return (
      <div className={`border-t border-border p-3 ${collapsed ? "flex justify-center" : "flex items-center gap-2"}`}>
        <div className="w-7 h-7 rounded-full bg-surface2 animate-pulse" />
        {!collapsed && <div className="flex-1 h-3 bg-surface2 rounded animate-pulse" />}
      </div>
    );
  }

  const email = user.primaryEmailAddress?.emailAddress ?? "";
  const name  = user.fullName ?? user.username ?? email.split("@")[0];

  return (
    <div className={`border-t border-border ${collapsed ? "p-2" : "p-3"}`}>
      <div className={`flex items-center ${collapsed ? "justify-center" : "gap-2"}`}>
        <UserButton
          afterSignOutUrl="/"
          appearance={{
            elements: {
              userButtonAvatarBox: "w-7 h-7",
            },
          }}
        />
        {!collapsed && (
          <div className="flex-1 min-w-0">
            <div className="text-[12px] font-medium text-ink truncate">{name}</div>
            <div className="text-[10.5px] text-muted truncate">{email}</div>
          </div>
        )}
      </div>
    </div>
  );
}
