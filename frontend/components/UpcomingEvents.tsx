"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type CalendarEvent } from "@/lib/api";

export default function UpcomingEvents() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);

  useEffect(() => {
    api
      .getCalendar(120)
      .then((page) => setEvents(page.events.filter((e) => e.phase !== "after").slice(0, 3)))
      .catch(() => setEvents([]));
  }, []);

  if (events.length === 0) return null;
  return (
    <Link
      href="/calendar"
      className="mb-4 flex flex-wrap items-center gap-3 rounded-md border border-orange-200 bg-orange-50 p-3 text-sm text-orange-900 hover:bg-orange-100"
    >
      <span className="font-medium">Sắp tới:</span>
      {events.map((e) => (
        <span key={`${e.key}-${e.start}`}>
          {e.name} ({e.days_until > 0 ? `${e.days_until} ngày` : "đang diễn ra"}) · {e.phase_label}
        </span>
      ))}
      <span className="ml-auto text-xs underline">Xem lịch mùa vụ →</span>
    </Link>
  );
}
