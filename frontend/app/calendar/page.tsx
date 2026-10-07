"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, api, type CalendarEvent, type CalendarPage } from "@/lib/api";

type Result = { key: string; data?: CalendarPage; error?: string };

const PHASE_STYLE: Record<CalendarEvent["phase"], string> = {
  upcoming: "bg-zinc-100 text-zinc-700",
  design: "bg-purple-100 text-purple-800",
  launch: "bg-blue-100 text-blue-800",
  push: "bg-green-100 text-green-800",
  cutoff: "bg-amber-100 text-amber-800",
  peak: "bg-red-100 text-red-800",
  after: "bg-zinc-100 text-zinc-500",
};

const TYPE_LABEL: Record<CalendarEvent["type"], string> = {
  holiday: "Lễ",
  occasion: "Dịp",
  awareness: "Tháng nhận thức",
  sale: "Sale TikTok Shop",
};

function shortDm(iso: string): string {
  const [, m, d] = iso.split("-");
  return `${d}/${m}`;
}

function shortDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

export default function CalendarPageView() {
  const [days, setDays] = useState(120);
  const [tick, setTick] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const key = `${days}#${tick}`;
  const loading = result?.key !== key;

  useEffect(() => {
    let cancelled = false;
    api
      .getCalendar(days)
      .then((data) => !cancelled && setResult({ key, data }))
      .catch((err) => !cancelled && setResult({ key, error: String(err) }));
    return () => {
      cancelled = true;
    };
  }, [days, key]);

  async function follow(keyword: string) {
    try {
      await api.addSeed(keyword);
      setMessage(`Đã thêm "${keyword}" vào watchlist — lần quét tới sẽ lấy dữ liệu cho ngách này.`);
      setTick((t) => t + 1);
    } catch (err) {
      setMessage(err instanceof ApiError && err.status === 409 ? `"${keyword}" đã có trong watchlist.` : String(err));
    }
  }

  const page = result?.data;

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-xl font-semibold">Lịch mùa vụ (Mỹ)</h1>
        <select
          className="rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
        >
          <option value={60}>60 ngày tới</option>
          <option value={120}>120 ngày tới</option>
          <option value={240}>240 ngày tới</option>
          <option value={365}>12 tháng tới</option>
        </select>
      </div>
      <p className="mb-4 text-xs text-zinc-500">
        Mốc tính lùi từ ngày sự kiện: thiết kế −8 tuần, lên sản phẩm −6 tuần, đẩy mạnh −4 tuần, hạn chót đặt hàng −
        {(page?.fulfillment_days ?? 10) + 3} ngày (thời gian in + giao POD + đệm 3 ngày, chỉnh trong backend/config/us_calendar.yaml).
      </p>
      {message && <p className="mb-3 rounded-md bg-zinc-100 p-3 text-sm">{message}</p>}
      {loading && <p className="text-sm text-zinc-500">Đang tải…</p>}
      {result?.error && !loading && <p className="text-sm text-red-600">Không tải được lịch: {result.error}</p>}

      <div className="space-y-4">
        {page?.events.map((event) => {
          const today = page.today;
          const deadline = event.phase === "peak" ? event.order_by : event.ship_by;
          return (
          <section key={`${event.key}-${event.start}`} className="rounded-lg border border-zinc-200 bg-white p-4">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold">{event.name}</h2>
              <span className="text-sm text-zinc-500">
                {shortDate(event.start)}
                {event.end !== event.start && <> – {shortDate(event.end)}</>}
              </span>
              <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-600">{TYPE_LABEL[event.type]}</span>
              <span className={`rounded px-1.5 py-0.5 text-xs ${PHASE_STYLE[event.phase]}`}>{event.phase_label}</span>
              <span className="ml-auto text-sm font-medium">
                {event.days_until > 0 ? `còn ${event.days_until} ngày` : event.phase === "after" ? "đã qua" : "đang diễn ra"}
              </span>
            </div>
            <p className="mt-2 text-sm">{event.advice}</p>
            {event.note && <p className="mt-1 text-xs text-zinc-500">{event.note}</p>}
            <p className="mt-2 text-xs text-zinc-500">
              {[
                event.design_start >= today && `Thiết kế từ ${shortDate(event.design_start)}`,
                event.launch_by >= today && `lên sản phẩm trước ${shortDate(event.launch_by)}`,
                event.push_from >= today && `đẩy mạnh từ ${shortDate(event.push_from)}`,
                deadline && deadline >= today && `Hạn chót đặt hàng ${shortDate(deadline)}`,
                event.end !== event.start && event.start <= today && today <= event.end && `đang diễn ra · kết thúc ${shortDm(event.end)}`,
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>

            {event.seed_ideas.length > 0 && (
              <div className="mt-3">
                <p className="mb-1 text-xs font-medium uppercase text-zinc-500">Ghép với ngách của bạn</p>
                <div className="flex flex-wrap gap-2">
                  {event.seed_ideas.map((idea) => (
                    <span
                      key={idea.keyword}
                      className="flex items-center gap-1 rounded-full border border-zinc-300 px-3 py-1 text-sm"
                    >
                      {idea.keyword_id ? (
                        <Link href={`/trends/${idea.keyword_id}`} className="hover:underline">
                          {idea.keyword}
                        </Link>
                      ) : (
                        idea.keyword
                      )}
                      {idea.score !== null && <span className="text-xs text-zinc-400">{Math.round(idea.score)}</span>}
                      {!idea.is_seed && (
                        <button onClick={() => follow(idea.keyword)} className="text-xs text-orange-600 hover:underline">
                          + Theo dõi
                        </button>
                      )}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {event.radar_matches.length > 0 && (
              <div className="mt-3">
                <p className="mb-1 text-xs font-medium uppercase text-zinc-500">Đang có trên Trend Radar</p>
                <div className="flex flex-wrap gap-2">
                  {event.radar_matches.map((m) => (
                    <Link
                      key={m.keyword_id}
                      href={`/trends/${m.keyword_id}`}
                      className="rounded-full bg-zinc-100 px-3 py-1 text-sm hover:bg-zinc-200"
                    >
                      {m.keyword} <span className="text-xs text-zinc-500">{Math.round(m.score)}</span>
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </section>
          );
        })}
      </div>
    </div>
  );
}
