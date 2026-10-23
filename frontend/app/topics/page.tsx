"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import IpBadge from "@/components/IpBadge";
import Sparkline from "@/components/Sparkline";
import { TAG_CHIP } from "@/components/SignalCard";
import { Button, Checkbox, Delta, EmptyState, HalftoneMeter, Notice, PageHeader, Select, Tabs } from "@/components/ui";
import { ApiError, api, type Topic, type TopicPage } from "@/lib/api";
import { formatNumber } from "@/lib/format";

type Scope = "all" | "new";
type Sort = "score" | "growth";
type Result = { data?: TopicPage; error?: string };

/** Score 1× (average listing) → 0 dots, 5× and above → 10 dots. */
function meterValue(score: number): number {
  return Math.min(Math.max((score - 1) / 4, 0), 1);
}

function anchor(key: string): string {
  return `topic-${key.replace(/[^a-z0-9]+/gi, "-")}`;
}

export default function TopicsPage() {
  return (
    <Suspense fallback={null}>
      <TopicsView />
    </Suspense>
  );
}

function TopicsView() {
  const focus = useSearchParams().get("key");
  const [result, setResult] = useState<Result | null>(null);
  const [scope, setScope] = useState<Scope>("all");
  const [sort, setSort] = useState<Sort>("score");
  const [hideIp, setHideIp] = useState(true);
  const [watched, setWatched] = useState<Set<string>>(new Set());
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    api
      .listTopics()
      .then((data) => setResult({ data }))
      .catch((err) => setResult({ error: String(err) }));
    api
      .listSeeds()
      .then((seeds) => setWatched(new Set(seeds.map((s) => s.keyword.toLowerCase()))))
      .catch(() => {});
  }, []);

  const all = useMemo(() => result?.data?.items ?? [], [result]);
  const visible = useMemo(() => {
    const kept = all.filter((t) => !(hideIp && t.ip_level === "red"));
    const scoped = scope === "new" ? kept.filter((t) => t.new) : kept;
    if (sort === "growth") {
      return [...scoped].sort(
        (a, b) => (a.growth === null ? 1 : 0) - (b.growth === null ? 1 : 0) || (b.growth ?? 0) - (a.growth ?? 0),
      );
    }
    return scoped;
  }, [all, hideIp, scope, sort]);
  const counts = useMemo(() => {
    const kept = all.filter((t) => !(hideIp && t.ip_level === "red"));
    return { all: kept.length, new: kept.filter((t) => t.new).length };
  }, [all, hideIp]);

  useEffect(() => {
    if (focus && visible.length) document.getElementById(anchor(focus))?.scrollIntoView({ block: "center" });
  }, [focus, visible.length]);

  async function watch(topic: Topic) {
    try {
      await api.addSeed(topic.key);
      setWatched((w) => new Set(w).add(topic.key.toLowerCase()));
      setMessage(null);
    } catch (err) {
      setMessage(
        err instanceof ApiError && err.status === 409
          ? `"${topic.key}" đã có trong Watchlist.`
          : `Không thêm được "${topic.key}" vào Watchlist: ${String(err)}`,
      );
    }
  }

  const lead = visible.slice(0, 3);
  const rest = visible.slice(3);
  const data = result?.data;

  return (
    <div>
      <PageHeader
        eyebrow={
          <>
            Ngách mới nổi
            {data?.date && <span className="font-mono">· {data.date}</span>}
          </>
        }
        title="Ngách đang được lưu nhiều lên"
        description="Listing Etsy cùng chủ đề, gom theo tag. Ngách tăng đều ở nhiều shop là lúc nên làm design — trước khi đông."
      />

      <div className="mb-4 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <Tabs<Scope>
          label="Phạm vi"
          value={scope}
          onChange={setScope}
          items={[
            { value: "all", label: "Tất cả", count: data ? counts.all : null },
            { value: "new", label: "Mới vào tuần này", count: data ? counts.new : null },
          ]}
          className="min-w-0 flex-1"
        />
        <div className="flex flex-wrap items-end gap-4 max-sm:w-full max-sm:[&>*]:flex-1">
          <Select label="Xếp theo" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
            <option value="score">Tốc độ lưu</option>
            <option value="growth">Tăng so tuần trước</option>
          </Select>
          <Checkbox
            className="h-9"
            label="Ẩn ngách dính thương hiệu"
            checked={hideIp}
            onChange={(e) => setHideIp(e.target.checked)}
          />
        </div>
      </div>

      <details className="group mb-6 text-xs leading-5 text-ink-2">
        <summary className="cursor-pointer list-none font-medium text-ink marker:hidden [&::-webkit-details-marker]:hidden">
          <span className="mr-1 inline-block transition-transform group-open:rotate-90" aria-hidden="true">
            ›
          </span>
          Cách gom và chấm điểm
        </summary>
        <ul className="mt-2 max-w-3xl list-disc space-y-1 pl-5">
          <li>Mỗi tag bỏ từ chung (shirt, tee, gift, women…) thành một ngách; ngách trùng ≥ 60% listing được gộp.</li>
          <li>Cần ≥ 5 listing của ≥ 3 shop, và không listing nào chiếm quá nửa lượt lưu tăng — một listing viral không phải ngách.</li>
          <li>
            Tốc độ 1× = listing trung bình. Ngách ít listing bị kéo về mức trung bình, nên điểm cao là đáng tin. Chấm
            đầy = từ 5×.
          </li>
          <li>
            &quot;Mới&quot; = không có trong danh sách 7 ngày trước. Ngưỡng chỉnh trong{" "}
            <span className="font-mono">backend/config/topics.yaml</span>.
          </li>
        </ul>
      </details>

      {message && (
        <Notice tone="error" className="mb-4">
          {message}
        </Notice>
      )}
      {result?.error && (
        <Notice tone="error" title="Không tải được danh sách ngách" className="mb-4">
          <span className="break-all font-mono text-xs">{result.error}</span>
        </Notice>
      )}
      {!result && <p className="py-6 text-sm text-ink-2">Đang tải…</p>}
      {data && visible.length === 0 && (
        <EmptyState
          title={!data.date ? "Chưa có ngách nào" : scope === "new" ? "Tuần này chưa có ngách mới" : "Không còn ngách sau khi lọc"}
          body={
            !data.date
              ? "Ngách được tính sau mỗi lần quét (8:00 và 20:00) và cần vài ngày lượt lưu của listing."
              : scope === "new"
                ? "Xem tab Tất cả, hoặc quay lại sau lần quét tới."
                : "Bỏ chọn “Ẩn ngách dính thương hiệu” để xem cả các ngách đó."
          }
        />
      )}

      {lead.length > 0 && (
        <section aria-label="Ba ngách dẫn đầu" className="mb-6 grid gap-4 md:grid-cols-3">
          {lead.map((t, i) => (
            <LeadCard
              key={t.key}
              topic={t}
              place={i + 1}
              focused={t.key === focus}
              watched={watched.has(t.key.toLowerCase())}
              onWatch={() => watch(t)}
            />
          ))}
        </section>
      )}

      {rest.length > 0 && (
        <section aria-label="Các ngách tiếp theo" className="overflow-hidden rounded-md border border-rule bg-sheet shadow-card">
          <div className="hidden grid-cols-[2.5rem_minmax(0,1fr)_9rem_6.5rem_7.5rem_12rem] items-center gap-4 border-b border-rule px-4 py-2 text-ink-2 lg:grid">
            <span className="eyebrow">#</span>
            <span className="eyebrow">Ngách</span>
            <span className="eyebrow">Tốc độ</span>
            <span className="eyebrow text-right">Lưu 7 ngày</span>
            <span className="eyebrow text-right">Quy mô</span>
            <span className="sr-only">Thao tác</span>
          </div>
          <ol className="divide-y divide-rule">
            {rest.map((t, i) => (
              <TopicRow
                key={t.key}
                topic={t}
                place={i + 4}
                focused={t.key === focus}
                watched={watched.has(t.key.toLowerCase())}
                onWatch={() => watch(t)}
              />
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}

type ItemProps = { topic: Topic; place: number; focused: boolean; watched: boolean; onWatch: () => void };

function Badges({ topic: t }: { topic: Topic }) {
  return (
    <>
      {t.new && (
        <span className="inline-flex rounded-full bg-cyan px-2 text-[11px] font-semibold leading-[18px] text-white">Mới</span>
      )}
      <IpBadge level={t.ip_level} />
    </>
  );
}

function WatchButton({ watched, onWatch, topic }: { watched: boolean; onWatch: () => void; topic: Topic }) {
  return (
    <Button
      size="sm"
      variant={watched ? "ghost" : "secondary"}
      disabled={watched}
      onClick={onWatch}
      aria-label={watched ? `Đang theo dõi ${topic.key}` : `Theo dõi ${topic.key}`}
    >
      {watched ? "✓ Đang theo dõi" : "+ Theo dõi"}
    </Button>
  );
}

function ResearchLink({ topic }: { topic: Topic }) {
  return (
    <Link
      href={`/niche?keyword=${encodeURIComponent(topic.key)}`}
      className="whitespace-nowrap text-xs font-medium text-ink underline decoration-rule underline-offset-4 hover:decoration-ink"
    >
      Phân tích ngách →
    </Link>
  );
}

/** Top-3 card: contact strip of the niche's best listings, then name, speed meter and the numbers behind it. */
function LeadCard({ topic: t, place, focused, watched, onWatch }: ItemProps) {
  return (
    <article
      id={anchor(t.key)}
      className={`flex min-w-0 flex-col overflow-hidden rounded-md border bg-sheet shadow-card ${
        focused ? "border-ink ring-2 ring-ink/15" : "border-rule"
      }`}
    >
      <div className="grid grid-cols-4 gap-px border-b border-rule bg-rule">
        {Array.from({ length: 4 }, (_, i) => t.products[i]).map((p, i) =>
          p ? (
            <a
              key={p.id}
              href={p.url}
              target="_blank"
              rel="noopener noreferrer"
              title={p.title}
              className="group/img relative aspect-[4/5] overflow-hidden bg-paper"
            >
              {p.image_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={p.image_url}
                  alt={p.title}
                  loading="lazy"
                  className="h-full w-full object-cover transition-transform duration-300 group-hover/img:scale-105"
                />
              )}
            </a>
          ) : (
            <div key={`empty-${i}`} className="aspect-[4/5] bg-paper" />
          ),
        )}
      </div>
      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex items-start gap-3">
          <span className="font-wider font-display text-3xl font-black leading-none text-rule" aria-label={`Hạng ${place}`}>
            {place}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <Badges topic={t} />
            </div>
            <h2 className="font-wide mt-1 font-display text-xl font-extrabold leading-6 text-ink">{t.key}</h2>
            {t.aliases.length > 0 && (
              <p className="mt-0.5 truncate text-xs text-ink-2">cùng nhóm: {t.aliases.slice(0, 3).join(", ")}</p>
            )}
          </div>
        </div>

        <div className="flex items-end justify-between gap-3 border-t border-rule pt-3">
          <div>
            <p className="eyebrow text-ink-2">Tốc độ lưu</p>
            <HalftoneMeter value={meterValue(t.score)} label={`${t.score.toFixed(1)}×`} className="mt-1" />
          </div>
          {t.series.length >= 2 && (
            <span title="Tốc độ theo ngày, 30 ngày">
              <Sparkline values={t.series.map((p) => p.score)} width={84} height={22} />
            </span>
          )}
        </div>

        <dl className="grid grid-cols-3 gap-2 font-mono text-[13px]">
          <div>
            <dt className="eyebrow text-[10px] text-ink-2">Lưu 7 ngày</dt>
            <dd className="font-medium text-ink">+{formatNumber(Math.round(t.gain_7d))}</dd>
          </div>
          <div>
            <dt className="eyebrow text-[10px] text-ink-2">So tuần trước</dt>
            <dd>
              <Delta value={t.growth} />
            </dd>
          </div>
          <div>
            <dt className="eyebrow text-[10px] text-ink-2">Listing · shop</dt>
            <dd className="text-ink">
              {t.listings} · {t.shops}
            </dd>
          </div>
        </dl>

        <div className="mt-auto flex items-center justify-between gap-2 pt-1">
          <ResearchLink topic={t} />
          <WatchButton topic={t} watched={watched} onWatch={onWatch} />
        </div>
      </div>
    </article>
  );
}

/** Rank 4+: one scannable line per niche (stacks on small screens). */
function TopicRow({ topic: t, place, focused, watched, onWatch }: ItemProps) {
  return (
    <li
      id={anchor(t.key)}
      className={`grid grid-cols-[1.5rem_minmax(0,1fr)] items-center gap-x-3 gap-y-2 px-4 py-3 lg:gap-x-4 lg:grid-cols-[2.5rem_minmax(0,1fr)_9rem_6.5rem_7.5rem_12rem] ${
        focused ? "bg-cyan/5" : "hover:bg-paper/60"
      }`}
    >
      <span className="font-mono text-sm text-ink-2">{place}</span>

      <div className="flex min-w-0 items-center gap-3">
        <div className="flex shrink-0 -space-x-2">
          {t.products.slice(0, 3).map((p) =>
            p.image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={p.id}
                src={p.image_url}
                alt=""
                loading="lazy"
                className="size-9 rounded-md border-2 border-sheet bg-paper object-cover"
              />
            ) : null,
          )}
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="truncate font-medium text-ink">{t.key}</span>
            <Badges topic={t} />
          </div>
          {t.aliases.length > 0 && (
            <div className="mt-0.5 flex flex-wrap gap-1">
              {t.aliases.slice(0, 2).map((a) => (
                <span key={a} className={`${TAG_CHIP} py-0`}>
                  {a}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Numbers: one wrapped line on small screens, columns on large ones. */}
      <div className="col-start-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[13px] lg:contents">
        <HalftoneMeter value={meterValue(t.score)} size="sm" label={`${t.score.toFixed(1)}×`} />
        <span className="text-right lg:block">
          <span className="text-ink">+{formatNumber(Math.round(t.gain_7d))}</span>
          {t.growth !== null && (
            <>
              {" "}
              <Delta value={t.growth} className="text-[11px]" />
            </>
          )}
        </span>
        <span className="text-right text-ink-2 lg:block">
          {t.listings} listing · {t.shops} shop
        </span>
      </div>

      <div className="col-start-2 flex items-center justify-between gap-3 lg:col-start-auto lg:justify-end">
        <span className="lg:hidden">
          <ResearchLink topic={t} />
        </span>
        <span className="hidden lg:inline">
          <Link
            href={`/niche?keyword=${encodeURIComponent(t.key)}`}
            className="mr-2 text-xs font-medium text-ink underline decoration-rule underline-offset-4 hover:decoration-ink"
            aria-label={`Phân tích ngách ${t.key}`}
          >
            Phân tích
          </Link>
        </span>
        <WatchButton topic={t} watched={watched} onWatch={onWatch} />
      </div>
    </li>
  );
}
