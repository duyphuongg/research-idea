"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import PressStatus from "./PressStatus";
import RegistrationMark from "./RegistrationMark";
import { api } from "@/lib/api";

/** Grouped by what the user is doing: today's follow-ups, finding ideas, digging into one niche/shop. */
type NavItem = { href: string; label: string };

export const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Hôm nay",
    items: [
      { href: "/alerts", label: "Tin mới" },
      { href: "/work", label: "Việc của tôi" },
      { href: "/watchlist", label: "Watchlist" },
    ],
  },
  {
    label: "Tìm ý tưởng",
    items: [
      { href: "/", label: "Trend Radar" },
      { href: "/topics", label: "Ngách mới nổi" },
      { href: "/signals", label: "Listing Signals" },
      { href: "/products", label: "Bán chạy" },
      { href: "/nfl", label: "NFL tuần này" },
      { href: "/calendar", label: "Lịch mùa vụ" },
    ],
  },
  {
    label: "Nghiên cứu sâu",
    items: [
      { href: "/niche", label: "Phân tích ngách" },
      { href: "/shops", label: "Shop" },
    ],
  },
];

const SETTINGS_ITEM: NavItem = { href: "/settings", label: "Cài đặt" };

export const NAV_ITEMS = [...NAV_GROUPS.flatMap((g) => g.items), SETTINGS_ITEM];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/" || pathname.startsWith("/trends");
  return pathname === href || pathname.startsWith(`${href}/`);
}

function Logo({ className = "" }: { className?: string }) {
  return (
    <Link href="/" className={`flex items-center gap-2 text-white ${className}`}>
      <RegistrationMark size={16} className="text-cyan" />
      <span className="font-wider font-display text-[13px] font-extrabold uppercase leading-none tracking-[0.06em]">
        POD Trend Radar
      </span>
    </Link>
  );
}

function NavLink({
  item,
  active,
  badge,
  linkRef,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  badge: number;
  linkRef?: RefObject<HTMLAnchorElement | null>;
  onNavigate: () => void;
}) {
  return (
    <li>
      <Link
        ref={linkRef}
        href={item.href}
        aria-current={active ? "page" : undefined}
        onClick={onNavigate}
        className={`relative flex items-center gap-3 px-5 py-2 text-sm transition-colors ${
          active ? "bg-white/[0.06] font-semibold text-white" : "text-white/70 hover:bg-white/[0.04] hover:text-white"
        }`}
      >
        <span aria-hidden="true" className={`absolute inset-y-1 left-0 w-[3px] ${active ? "bg-cyan" : "bg-transparent"}`} />
        {item.label}
        {badge > 0 && (
          <>
            <span className="ml-auto rounded-full bg-cyan px-1.5 font-mono text-[11px] font-medium leading-5 text-ink">
              {badge > 99 ? "99+" : badge}
            </span>
            <span className="sr-only"> chưa đọc</span>
          </>
        )}
      </Link>
    </li>
  );
}

/** Fixed 232px ink sidebar on desktop; top bar + drawer below 1024px. */
export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const menuButton = useRef<HTMLButtonElement>(null);
  const firstLink = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .unreadAlerts()
      .then((r) => !cancelled && setUnread(r.unread))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  useEffect(() => {
    const reset = () => setUnread(0);
    window.addEventListener("alerts:read", reset);
    return () => window.removeEventListener("alerts:read", reset);
  }, []);

  useEffect(() => {
    if (!open) return;
    firstLink.current?.focus();
    const button = menuButton.current;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      button?.focus();
    };
  }, [open]);

  return (
    <div className="min-h-screen">
      <a
        href="#main"
        className="sr-only z-[60] rounded-md bg-ink px-3 py-2 text-sm text-white focus:not-sr-only focus:fixed focus:left-3 focus:top-3"
      >
        Bỏ qua điều hướng
      </a>

      {/* Mobile top bar */}
      <div className="on-ink sticky top-0 z-[45] flex h-14 items-center justify-between bg-ink px-4 lg:hidden">
        <Logo />
        <button
          ref={menuButton}
          type="button"
          aria-expanded={open}
          aria-controls="app-sidebar"
          onClick={() => setOpen((o) => !o)}
          className="inline-flex h-9 items-center gap-2 rounded-md border border-white/20 px-3 text-sm text-white hover:bg-white/10"
        >
          <svg width="16" height="12" viewBox="0 0 16 12" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5">
            {open ? <path d="M3 1l10 10M13 1L3 11" /> : <path d="M0 1h16M0 6h16M0 11h16" />}
          </svg>
          {open ? "Đóng" : "Menu"}
        </button>
      </div>

      {/* Drawer backdrop */}
      {open && (
        <div aria-hidden="true" className="fixed inset-0 z-40 bg-ink/50 lg:hidden" onClick={() => setOpen(false)} />
      )}

      <aside
        id="app-sidebar"
        aria-label="Điều hướng chính"
        className={`on-ink fixed inset-y-0 left-0 z-50 w-[264px] max-w-[85vw] flex-col bg-ink text-white lg:z-20 lg:flex lg:w-[232px] ${
          open ? "flex" : "hidden"
        }`}
      >
        <div className="flex h-14 items-center px-5 lg:h-[72px]">
          <Logo />
        </div>
        <nav className="flex-1 overflow-y-auto pb-3 [scrollbar-color:rgb(255_255_255/0.2)_transparent] [scrollbar-width:thin]">
          {NAV_GROUPS.map((group, gi) => (
            <div key={group.label} className={gi > 0 ? "mt-4" : ""}>
              <p className="eyebrow px-5 pb-1 text-[10px] text-white/40">{group.label}</p>
              <ul>
                {group.items.map((item) => (
                  <NavLink
                    key={item.href}
                    item={item}
                    active={isActive(pathname, item.href)}
                    badge={item.href === "/alerts" ? unread : 0}
                    linkRef={item.href === NAV_GROUPS[0].items[0].href ? firstLink : undefined}
                    onNavigate={() => setOpen(false)}
                  />
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <div className="border-t border-white/10">
          <PressStatus />
          <ul className="pb-2">
            <NavLink
              item={SETTINGS_ITEM}
              active={isActive(pathname, SETTINGS_ITEM.href)}
              badge={0}
              onNavigate={() => setOpen(false)}
            />
          </ul>
        </div>
      </aside>

      <div className="lg:pl-[232px]">
        <main id="main" tabIndex={-1} className="mx-auto max-w-[1280px] px-4 py-6 focus:outline-none lg:px-8 lg:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}
