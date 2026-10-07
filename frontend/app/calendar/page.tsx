"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, api, type CalendarEvent, type CalendarPage } from "@/lib/api";
import { Button, Card, EmptyState, Notice, PageHeader, Select, StatusBadge } from "@/components/ui";

type Result = { key: string; data?: CalendarPage; error?: string };

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
  const today = page?.today ?? "";

  return (
    <div>
      <PageHeader
        eyebrow={`Lịch mùa vụ${page ? ` · ${shortDate(page.today)}` : ""}`}
        title="Lịch mùa vụ (Mỹ)"
        description={
          <>
            Mốc tính lùi từ ngày sự kiện: thiết kế −8 tuần, lên sản phẩm −6 tuần, đẩy mạnh −4 tuần, hạn chót đặt hàng −
            {(page?.fulfillment_days ?? 10) + 3} ngày (thời gian in + giao POD + đệm 3 ngày, chỉnh trong backend/config/us_calendar.yaml).
          </>
        }
        actions={
          <Select aria-label="Khoảng thời gian" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={60}>60 ngày tới</option>
            <option value={120}>120 ngày tới</option>
            <option value={240}>240 ngày tới</option>
            <option value={365}>12 tháng tới</option>
          </Select>
        }
      />
      {message && <Notice className="mb-4">{message}</Notice>}
      {loading && <p className="text-sm text-ink-2">Đang tải…</p>}
      {result?.error && !loading && <Notice tone="error">Không tải được lịch: {result.error}</Notice>}
      {page && page.events.length === 0 && !loading && (
        <EmptyState title="Không có sự kiện nào trong khoảng này" body="Thử chọn khoảng thời gian dài hơn." />
      )}

      <ol className="space-y-5">
        {page?.events.map((event) => {
          const deadline = event.phase === "peak" ? event.order_by : event.ship_by;
          const ongoing = event.end !== event.start && event.start <= today && today <= event.end;
          const milestones = [
            event.design_start >= today && `Thiết kế từ ${shortDate(event.design_start)}`,
            event.launch_by >= today && `lên sản phẩm trước ${shortDate(event.launch_by)}`,
            event.push_from >= today && `đẩy mạnh từ ${shortDate(event.push_from)}`,
            deadline && deadline >= today && `Hạn chót đặt hàng ${shortDate(deadline)}`,
          ].filter(Boolean) as string[];
          return (
            <li key={`${event.key}-${event.start}`} className="grid gap-2 md:grid-cols-[9.5rem_1fr] md:gap-6">
              <div className="md:pt-4 md:text-right">
                <p className="font-mono text-sm font-medium text-ink">
                  {shortDate(event.start)}
                  {event.end !== event.start && <span className="text-ink-2"> – {shortDm(event.end)}</span>}
                </p>
                <p className="mt-0.5 text-xs text-ink-2">
                  {ongoing
                    ? `đang diễn ra · kết thúc ${shortDm(event.end)}`
                    : event.days_until > 0
                      ? `còn ${event.days_until} ngày`
                      : event.phase === "after"
                        ? "đã qua"
                        : "đang diễn ra"}
                </p>
              </div>
              <Card className={event.phase === "after" ? "opacity-70" : ""}>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                  <h2 className="font-display text-lg font-bold leading-6 text-ink">{event.name}</h2>
                  <span className="eyebrow text-ink-2">{TYPE_LABEL[event.type]}</span>
                  <StatusBadge kind="phase" status={event.phase} label={event.phase_label} className="ml-auto" />
                </div>
                <p className="mt-2 text-sm text-ink">{event.advice}</p>
                {event.note && <p className="mt-1 text-xs text-ink-2">{event.note}</p>}
                {milestones.length > 0 && (
                  <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t border-rule pt-3 font-mono text-xs text-ink-2">
                    {milestones.map((m) => (
                      <li key={m}>{m}</li>
                    ))}
                  </ul>
                )}

                {event.seed_ideas.length > 0 && (
                  <div className="mt-3">
                    <p className="eyebrow mb-1.5 text-ink-2">Ghép với ngách của bạn</p>
                    <div className="flex flex-wrap items-center gap-2">
                      {event.seed_ideas.map((idea) => (
                        <span
                          key={idea.keyword}
                          className="inline-flex items-center gap-1.5 rounded-full border border-rule bg-paper py-0.5 pl-3 pr-1 text-sm text-ink"
                        >
                          {idea.keyword_id ? (
                            <Link href={`/trends/${idea.keyword_id}`} className="hover:underline">
                              {idea.keyword}
                            </Link>
                          ) : (
                            idea.keyword
                          )}
                          {idea.score !== null && <span className="font-mono text-xs text-ink-2">{Math.round(idea.score)}</span>}
                          {idea.is_seed ? (
                            <span className="pr-2" />
                          ) : (
                            <Button variant="ghost" size="sm" className="h-6 rounded-full" onClick={() => follow(idea.keyword)}>
                              + Theo dõi
                            </Button>
                          )}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {event.radar_matches.length > 0 && (
                  <div className="mt-3">
                    <p className="eyebrow mb-1.5 text-ink-2">Đang có trên Trend Radar</p>
                    <div className="flex flex-wrap gap-2">
                      {event.radar_matches.map((m) => (
                        <Link
                          key={m.keyword_id}
                          href={`/trends/${m.keyword_id}`}
                          className="inline-flex items-center gap-1.5 rounded-full border border-rule bg-sheet px-3 py-0.5 text-sm text-ink hover:border-ink-2"
                        >
                          {m.keyword} <span className="font-mono text-xs text-ink-2">{Math.round(m.score)}</span>
                        </Link>
                      ))}
                    </div>
                  </div>
                )}
              </Card>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
