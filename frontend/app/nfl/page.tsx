"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import NflMoments from "@/components/NflMoments";
import { CARD_CLASS } from "@/components/SignalCard";
import { Button, EmptyState, Notice, PageHeader, Select } from "@/components/ui";
import { api, type NflPage, type NflStandout, type NflWeek } from "@/lib/api";
import { formatInt, formatNumber } from "@/lib/format";

type SortKey = "potential" | "points" | "etsy";

const SORT_LABEL: Record<SortKey, string> = {
  potential: "Tiềm năng",
  points: "Điểm thi đấu",
  etsy: "Etsy listing",
};

const CATEGORY_LABEL: Record<string, string> = {
  passingYards: "Chuyền",
  rushingYards: "Chạy",
  receivingYards: "Bắt bóng",
};

const LINK_CLASS = "font-medium text-ink underline-offset-2 hover:underline";

function weekKey(w: { season: number; season_type: number; week: number }): string {
  return `${w.season}-${w.season_type}-${w.week}`;
}

function weekLabel(w: NflWeek): string {
  const base = w.season_type === 3 ? `Playoffs tuần ${w.week} · ${w.season}` : `Tuần ${w.week} · ${w.season}`;
  return `${base} (${w.games} trận)`;
}

function toInt(v: string | null): number | undefined {
  if (v === null || v === "") return undefined;
  const n = Number(v);
  return Number.isInteger(n) ? n : undefined;
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

function sortItems(items: NflStandout[], sort: SortKey): NflStandout[] {
  const copy = [...items];
  if (sort === "points") copy.sort((a, b) => b.points - a.points);
  else if (sort === "etsy") copy.sort((a, b) => (b.etsy_listings ?? -1) - (a.etsy_listings ?? -1));
  else copy.sort((a, b) => b.potential - a.potential);
  return copy;
}

export default function NflPageRoute() {
  return (
    <Suspense fallback={null}>
      <NflView />
    </Suspense>
  );
}

type Result = { key: string; data?: NflPage; error?: string };

function NflView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const season = toInt(params.get("season"));
  const seasonType = toInt(params.get("season_type"));
  const week = toInt(params.get("week"));

  const [result, setResult] = useState<Result | null>(null);
  const [tick, setTick] = useState(0);
  const [sort, setSort] = useState<SortKey>("potential");
  const key = `${season ?? ""}|${seasonType ?? ""}|${week ?? ""}#${tick}`;
  const loading = result?.key !== key;

  useEffect(() => {
    let cancelled = false;
    api
      .getNflStandouts({ season, season_type: seasonType, week })
      .then((data) => !cancelled && setResult({ key, data }))
      .catch((err) => !cancelled && setResult({ key, error: String(err) }));
    return () => {
      cancelled = true;
    };
  }, [key, season, seasonType, week]);

  // Keep showing the previous week while the next one loads.
  const data = result?.data;
  const items = useMemo(() => sortItems(data?.items ?? [], sort), [data, sort]);
  const selected =
    data && data.season !== null && data.season_type !== null && data.week !== null
      ? weekKey({ season: data.season, season_type: data.season_type, week: data.week })
      : "";

  function selectWeek(value: string) {
    const w = data?.weeks.find((x) => weekKey(x) === value);
    if (!w) return;
    const q = new URLSearchParams({ season: String(w.season), season_type: String(w.season_type), week: String(w.week) });
    router.push(`${pathname}?${q}`, { scroll: false });
  }

  return (
    <div>
      <PageHeader
        eyebrow="NFL"
        title="Cầu thủ nổi bật tuần này"
        description="Cầu thủ chơi hay nhất tuần, xếp theo tiềm năng làm áo — kết hợp phong độ, gợi ý tìm kiếm Google và số listing trên Etsy."
        actions={
          data && (
            <>
              {data.weeks.length > 0 && (
                <Select label="Tuần" value={selected} onChange={(e) => selectWeek(e.target.value)}>
                  {selected === "" && <option value="">—</option>}
                  {data.weeks.map((w) => (
                    <option key={weekKey(w)} value={weekKey(w)}>
                      {weekLabel(w)}
                    </option>
                  ))}
                </Select>
              )}
              <Select label="Sắp xếp" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
                {(Object.keys(SORT_LABEL) as SortKey[]).map((k) => (
                  <option key={k} value={k}>
                    {SORT_LABEL[k]}
                  </option>
                ))}
              </Select>
            </>
          )
        }
      />

      <p className="mb-4 text-xs leading-5 text-ink-2">
        Tên, số áo, hình cầu thủ và logo đội thuộc bản quyền NFL/NFLPA — dùng làm cảm hứng, tránh in trực tiếp.
      </p>

      <NflMoments />

      {loading && !data && <p className="py-6 text-sm text-ink-2">Đang tải…</p>}
      {!loading && result?.error && (
        <Notice
          tone="error"
          title="Không tải được dữ liệu"
          className="mb-4"
          action={
            <Button size="sm" onClick={() => setTick((t) => t + 1)}>
              Thử lại
            </Button>
          }
        >
          <span className="break-all font-mono text-xs">{result.error}</span>
        </Notice>
      )}

      {data && items.length === 0 && (
        <EmptyState
          title="Chưa có dữ liệu NFL"
          body="Chưa có dữ liệu NFL — có sau lần quét tới (8:00 / 20:00) hoặc bấm Quét ngay ở Cài đặt."
          action={
            <Link href="/settings" className={LINK_CLASS}>
              Mở Cài đặt
            </Link>
          }
        />
      )}

      {items.length > 0 && (
        <div
          className={`grid grid-cols-1 gap-4 transition-opacity sm:grid-cols-2 xl:grid-cols-3 ${loading ? "opacity-60" : ""}`}
        >
          {items.map((item) => (
            <PlayerCard key={item.athlete_id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

function Headshot({ src, name }: { src: string | null; name: string }) {
  const [failed, setFailed] = useState(false);
  return (
    <div className="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-full border border-rule bg-paper">
      {src && !failed ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt={name}
          loading="lazy"
          className="h-full w-full object-cover"
          onError={() => setFailed(true)}
        />
      ) : (
        <span aria-hidden="true" className="font-display text-lg font-extrabold text-ink-2">
          {initials(name)}
        </span>
      )}
    </div>
  );
}

function PotentialBar({ value }: { value: number }) {
  const v = Math.min(Math.max(Math.round(value), 0), 100);
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="eyebrow text-[10px] leading-4 text-ink-2">Tiềm năng</span>
        <span className="font-mono text-sm font-semibold text-ink">
          {v}
          <span className="text-xs font-normal text-ink-2">/100</span>
        </span>
      </div>
      <div
        role="meter"
        aria-label="Tiềm năng"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={v}
        className="mt-1 h-1.5 overflow-hidden rounded-full bg-rule"
      >
        <div className={`h-full rounded-full ${v >= 70 ? "bg-magenta" : "bg-ink"}`} style={{ width: `${v}%` }} />
      </div>
    </div>
  );
}

function PlayerCard({ item }: { item: NflStandout }) {
  const meta = [item.team, item.position].filter(Boolean).join(" · ");
  const etsyUrl = `https://www.etsy.com/search?q=${encodeURIComponent(`${item.name} shirt`)}`;
  return (
    <article className={CARD_CLASS}>
      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex items-start gap-3">
          <Headshot src={item.headshot_url} name={item.name} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <h2 className="truncate font-display text-base font-extrabold leading-6 text-ink">{item.name}</h2>
              {item.trending && (
                <span className="whitespace-nowrap rounded-full border border-magenta/40 bg-magenta/10 px-1.5 text-[11px] font-medium leading-4 text-ink">
                  🔥 Đang trend
                </span>
              )}
            </div>
            <p className="truncate text-xs text-ink-2">
              {meta || "—"}
              {item.jersey && <span className="font-mono"> #{item.jersey}</span>}
            </p>
            {item.games.length > 0 && <p className="truncate text-[11px] leading-4 text-ink-2">{item.games.join(" · ")}</p>}
          </div>
        </div>

        {item.lines.length > 0 && (
          <ul className="space-y-1 border-t border-rule pt-2">
            {item.lines.map((l) => (
              <li key={l.category} className="flex items-baseline gap-2 text-sm">
                <span className="eyebrow w-16 shrink-0 text-[10px] leading-4 text-ink-2">
                  {CATEGORY_LABEL[l.category] ?? l.category}
                </span>
                <span className="min-w-0 font-mono text-[13px] text-ink">{l.stat_line}</span>
              </li>
            ))}
          </ul>
        )}

        <div className="space-y-2 border-t border-rule pt-2">
          <p className="font-mono text-xs text-ink-2">
            <span className="font-medium text-ink">{formatNumber(Math.round(item.points * 10) / 10)}</span> điểm
          </p>
          <PotentialBar value={item.potential} />
          <p className="flex flex-wrap gap-x-3 text-xs text-ink-2">
            <span>
              Etsy:{" "}
              <span className="font-mono text-ink" title={formatInt(item.etsy_listings)}>
                {formatNumber(item.etsy_listings)}
              </span>{" "}
              listing
            </span>
            <span>
              Google: <span className="font-mono text-ink">{item.merch_suggestions ?? "—"}</span> gợi ý áo
            </span>
          </p>
        </div>

        <div className="mt-auto flex flex-wrap gap-x-4 gap-y-1 border-t border-rule pt-2 text-xs">
          {item.player_url && (
            <a href={item.player_url} target="_blank" rel="noopener noreferrer" className={LINK_CLASS}>
              ESPN ↗
            </a>
          )}
          <a href={etsyUrl} target="_blank" rel="noopener noreferrer" className={LINK_CLASS}>
            Etsy ↗
          </a>
          <Link href={`/niche?keyword=${encodeURIComponent(item.name.toLowerCase())}`} className={LINK_CLASS}>
            Phân tích ngách
          </Link>
        </div>
      </div>
    </article>
  );
}
