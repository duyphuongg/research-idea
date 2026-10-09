"use client";

import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";
import IpBadge from "@/components/IpBadge";
import { Button, EmptyState, Notice, Section } from "@/components/ui";
import { api, type NflMoment, type NflMomentsPage } from "@/lib/api";
import { formatInt, formatNumber, timeAgo } from "@/lib/format";

const LINK_CLASS = "font-medium text-ink underline-offset-2 hover:underline";
const DEFAULT_VISIBLE = 8;
/** Traffic at or above this gets an accent border. */
const HOT_TRAFFIC = 20000;
const DAYS = 7;

/** "20.000+ lượt tìm" — Google Trends traffic is a lower bound. */
function formatTraffic(n: number): string {
  return `${Math.round(n).toLocaleString("vi-VN")}+ lượt tìm`;
}

type Result = { tick: number; data?: NflMomentsPage; error?: string };

/** "Khoảnh khắc đang hot": NFL searches rising on Google Trends US. Loads independently of the player list. */
export default function NflMoments() {
  const [tick, setTick] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [expanded, setExpanded] = useState(false);
  const loading = result?.tick !== tick;

  useEffect(() => {
    let cancelled = false;
    api
      .getNflMoments(DAYS)
      .then((data) => !cancelled && setResult({ tick, data }))
      .catch((err) => !cancelled && setResult({ tick, error: String(err) }));
    return () => {
      cancelled = true;
    };
  }, [tick]);

  const items = result?.data?.items ?? [];
  const visible = expanded ? items : items.slice(0, DEFAULT_VISIBLE);

  return (
    <Section
      id="nfl-moments"
      title="Khoảnh khắc đang hot"
      className="mb-8"
      aside={items.length > 0 ? <span className="font-mono">{items.length} khoảnh khắc</span> : undefined}
    >
      <p className="text-xs leading-5 text-ink-2">
        Tìm kiếm NFL đang lên top Google Mỹ (quét mỗi giờ) — tình huống tranh cãi, chấn thương, phát ngôn…
      </p>

      {loading && !result?.data && <p className="py-4 text-sm text-ink-2">Đang tải…</p>}

      {!loading && result?.error && (
        <Notice
          tone="error"
          title="Không tải được khoảnh khắc NFL"
          action={
            <Button size="sm" onClick={() => setTick((t) => t + 1)}>
              Thử lại
            </Button>
          }
        >
          <span className="break-all font-mono text-xs">{result.error}</span>
        </Notice>
      )}

      {!loading && result?.data && items.length === 0 && (
        <EmptyState
          title="Chưa có khoảnh khắc NFL"
          body="Chưa có khoảnh khắc NFL nào trong 7 ngày — app quét Google Trends mỗi giờ."
        />
      )}

      {visible.length > 0 && (
        <ul className="space-y-2">
          {visible.map((m) => (
            <MomentRow key={m.id} moment={m} />
          ))}
        </ul>
      )}

      {items.length > DEFAULT_VISIBLE && (
        <div className="flex justify-center">
          <Button size="sm" variant="ghost" onClick={() => setExpanded((e) => !e)}>
            {expanded ? "Thu gọn" : `Xem thêm (${items.length - DEFAULT_VISIBLE})`}
          </Button>
        </div>
      )}
    </Section>
  );
}

function MomentPicture({ moment }: { moment: NflMoment }) {
  const candidates = [moment.picture_url, moment.player?.headshot_url].filter((s): s is string => Boolean(s));
  const [failedCount, setFailedCount] = useState(0);
  const src = candidates[failedCount];
  return (
    <div className="flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-md border border-rule bg-paper">
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={src}
          src={src}
          alt=""
          loading="lazy"
          className="h-full w-full object-cover"
          onError={() => setFailedCount((c) => c + 1)}
        />
      ) : (
        <span aria-hidden="true" className="text-2xl">
          🏈
        </span>
      )}
    </div>
  );
}

function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="whitespace-nowrap rounded-full border border-rule bg-paper px-1.5 text-[11px] font-medium leading-4 text-ink">
      {children}
    </span>
  );
}

function MomentRow({ moment }: { moment: NflMoment }) {
  const [showNews, setShowNews] = useState(false);
  const hot = moment.traffic >= HOT_TRAFFIC;
  const [first, ...rest] = moment.news;
  const p = moment.player;
  const playerPrefix = p ? [p.team, p.position].filter(Boolean).join(" · ") : "";
  const etsyUrl = `https://www.etsy.com/search?q=${encodeURIComponent(`${moment.query} shirt`)}`;

  return (
    <li
      className={`flex gap-3 rounded-md border border-rule bg-sheet p-3 shadow-card transition-colors hover:border-ink-2 ${
        hot ? "border-l-4 border-l-magenta hover:border-l-magenta" : ""
      }`}
    >
      <MomentPicture moment={moment} />
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <h3 className="min-w-0 break-words font-display text-[15px] font-extrabold leading-5 text-ink">
            {moment.query}
          </h3>
          <IpBadge level={moment.ip_level} />
          {p ? (
            <Chip>{playerPrefix ? `${playerPrefix} ${p.name}` : p.name}</Chip>
          ) : (
            moment.team && <Chip>{moment.team}</Chip>
          )}
        </div>
        <p className="flex flex-wrap gap-x-3 font-mono text-xs text-ink-2">
          <span className={hot ? "font-semibold text-magenta" : "text-ink"}>{formatTraffic(moment.traffic)}</span>
          <span title={moment.last_seen}>{timeAgo(moment.last_seen)}</span>
        </p>

        {first && (
          <div className="text-sm leading-5">
            <NewsLine title={first.title} url={first.url} source={first.source} />
            {rest.length > 0 && (
              <>
                {" "}
                <button
                  type="button"
                  onClick={() => setShowNews((s) => !s)}
                  aria-expanded={showNews}
                  className="whitespace-nowrap text-xs font-medium text-ink-2 underline-offset-2 hover:text-ink hover:underline"
                >
                  {showNews ? "Ẩn bớt" : `+${rest.length} tin`}
                </button>
              </>
            )}
            {showNews && rest.length > 0 && (
              <ul className="mt-1 space-y-0.5 border-l border-rule pl-2">
                {rest.map((n, i) => (
                  <li key={`${n.url ?? n.title}-${i}`}>
                    <NewsLine title={n.title} url={n.url} source={n.source} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-0.5 text-xs">
          <span className="text-ink-2">
            Etsy:{" "}
            <span className="font-mono text-ink" title={formatInt(moment.etsy_listings)}>
              {formatNumber(moment.etsy_listings)}
            </span>{" "}
            listing
          </span>
          <a href={etsyUrl} target="_blank" rel="noopener noreferrer" className={LINK_CLASS}>
            Etsy ↗
          </a>
          <Link href={`/niche?keyword=${encodeURIComponent(moment.query)}`} className={LINK_CLASS}>
            Phân tích ngách
          </Link>
        </div>
      </div>
    </li>
  );
}

function NewsLine({ title, url, source }: { title: string; url: string | null; source: string | null }) {
  return (
    <span>
      {url ? (
        <a href={url} target="_blank" rel="noopener noreferrer" className="text-ink underline-offset-2 hover:underline">
          {title}
        </a>
      ) : (
        <span className="text-ink">{title}</span>
      )}
      {source && <span className="text-xs text-ink-2"> — {source}</span>}
    </span>
  );
}
