"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/ui";
import { api, type CalendarEvent } from "@/lib/api";

const PHASE_RANK: Record<CalendarEvent["phase"], number> = {
  push: 0,
  launch: 1,
  design: 2,
  peak: 3,
  cutoff: 4,
  upcoming: 5,
  after: 6,
};

function pickUpcoming(events: CalendarEvent[], today: string): CalendarEvent[] {
  return events
    .filter((e) => e.phase !== "after" && !(e.phase === "peak" && (e.order_by === null || e.order_by < today)))
    .sort((a, b) => PHASE_RANK[a.phase] - PHASE_RANK[b.phase] || a.start.localeCompare(b.start))
    .slice(0, 3);
}

export default function UpcomingEvents() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);

  useEffect(() => {
    api
      .getCalendar(120)
      .then((page) => setEvents(pickUpcoming(page.events, page.today)))
      .catch(() => setEvents([]));
  }, []);

  if (events.length === 0) return null;
  return (
    <section aria-labelledby="upcoming-title" className="mb-6">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h2 id="upcoming-title" className="eyebrow text-ink-2">
          Sắp tới
        </h2>
        <Link href="/calendar" className="text-xs text-ink-2 underline-offset-2 hover:text-ink hover:underline">
          Xem lịch mùa vụ →
        </Link>
      </div>
      <ul className="grid gap-2 sm:grid-cols-3">
        {events.map((e) => (
          <li key={`${e.key}-${e.start}`}>
            <Link
              href="/calendar"
              className="flex h-full items-center gap-3 rounded-md border border-rule bg-sheet px-3 py-2.5 shadow-card transition-colors hover:border-ink-2"
            >
              <span className="flex w-12 shrink-0 flex-col items-center border-r border-rule pr-3 text-center">
                {e.days_until > 0 ? (
                  <>
                    <span className="font-mono text-lg font-medium leading-6 text-ink">{e.days_until}</span>
                    <span className="text-[11px] leading-4 text-ink-2">ngày</span>
                  </>
                ) : (
                  <span className="text-[11px] font-medium leading-4 text-ink">đang diễn ra</span>
                )}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold text-ink">{e.name}</span>
                <StatusBadge kind="phase" status={e.phase} className="mt-1" />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
