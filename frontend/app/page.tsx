"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import CompetitionBadge from "@/components/CompetitionBadge";
import Sparkline from "@/components/Sparkline";
import SourceHealthBanner from "@/components/SourceHealthBanner";
import UpcomingEvents from "@/components/UpcomingEvents";
import WorkStatus from "@/components/WorkStatus";
import {
  Button,
  ButtonLink,
  Card,
  Checkbox,
  Delta,
  EmptyState,
  HalftoneMeter,
  Notice,
  PageHeader,
  Select,
  SourceChip,
} from "@/components/ui";
import { ApiError, api, type TrendPage, type TrendQuery, type TrendSort } from "@/lib/api";
import { SOURCE_LABEL, formatInt, formatNumber } from "@/lib/format";

type Result = { key: string; data?: TrendPage; error?: string };

/** "2026-10-07" → "07/10/2026". */
function formatDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const [y, m, d] = iso.split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
}

const TH = "eyebrow whitespace-nowrap px-4 py-2.5 text-left font-bold text-ink-2";
const TD = "px-4 py-2.5 align-middle";

export default function TrendRadarPage() {
  const [query, setQuery] = useState<TrendQuery>({ pod_only: true, limit: 100 });
  const [tick, setTick] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const key = `${JSON.stringify(query)}#${tick}`;
  const loading = result?.key !== key;

  useEffect(() => {
    let cancelled = false;
    api
      .listTrends(query)
      .then((data) => !cancelled && setResult({ key, data }))
      .catch((err) => !cancelled && setResult({ key, error: String(err) }));
    return () => {
      cancelled = true;
    };
  }, [key, query]);

  async function follow(keyword: string) {
    try {
      await api.addSeed(keyword);
      setMessage(`Đã thêm "${keyword}" vào watchlist — lần quét tới sẽ lấy sản phẩm Etsy (shop US) cho keyword này.`);
      setTick((t) => t + 1);
    } catch (err) {
      setMessage(err instanceof ApiError && err.status === 409 ? `"${keyword}" đã có trong watchlist.` : String(err));
    }
  }

  const items = result?.data?.items ?? [];
  const dataDate = formatDate(result?.data?.date);

  return (
    <div>
      <PageHeader
        eyebrow={<>Trend Radar{dataDate && <> · <span className="font-mono">{dataDate}</span></>}</>}
        title="Ngách đang lên"
        description="Chọn ngách để theo dõi và lên thiết kế — xếp theo điểm thị trường Mỹ."
      />
      <SourceHealthBanner />
      <UpcomingEvents />

      <Card className="mb-4 flex flex-col items-start gap-3 sm:flex-row sm:flex-wrap sm:items-end">
        <Select
          label="Nguồn"
          value={query.source ?? ""}
          onChange={(e) => setQuery((q) => ({ ...q, source: e.target.value || undefined }))}
        >
          <option value="">Tất cả nguồn</option>
          {Object.entries(SOURCE_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
        <Select
          label="Loại keyword"
          value={query.origin ?? ""}
          onChange={(e) =>
            setQuery((q) => ({ ...q, origin: (e.target.value || undefined) as TrendQuery["origin"] }))
          }
        >
          <option value="">Seed + khám phá</option>
          <option value="seed">Chỉ seed</option>
          <option value="discovered">Chỉ ngách khám phá</option>
        </Select>
        <Select
          label="Sắp xếp"
          value={query.sort ?? "score"}
          onChange={(e) =>
            setQuery((q) => ({ ...q, sort: e.target.value === "score" ? undefined : (e.target.value as TrendSort) }))
          }
        >
          <option value="score">Điểm</option>
          <option value="opportunity">Cơ hội (nhu cầu cao, ít cạnh tranh)</option>
        </Select>
        <Checkbox
          label="Chỉ POD"
          className="sm:h-9"
          checked={query.pod_only ?? true}
          onChange={(e) => setQuery((q) => ({ ...q, pod_only: e.target.checked }))}
        />
        <p className="text-xs leading-5 text-ink-2 sm:ml-auto sm:max-w-md sm:text-right">
          Điểm 0–100 = nhu cầu (35%) + đà tăng (45%) + ít cạnh tranh (20%), tính trên dữ liệu thị trường Mỹ: Etsy (chỉ
          shop US), Google gợi ý (US), Google xu hướng ngày (US). Đà tăng cần ≥ 8 ngày dữ liệu.
        </p>
      </Card>

      {message && (
        <Notice tone="info" className="mb-4">
          {message}
        </Notice>
      )}
      {result?.error && !loading && (
        <Notice tone="error" title="Không tải được dữ liệu" className="mb-4">
          <span className="font-mono text-xs">{result.error}</span>
        </Notice>
      )}
      {loading && (
        <Card className="mb-4 text-sm text-ink-2" role="status">
          Đang tải…
        </Card>
      )}
      {!loading && result?.data && items.length === 0 && (
        <EmptyState
          title="Chưa có điểm"
          body={<>Thêm keyword trong Cài đặt rồi bấm &quot;Quét ngay&quot;.</>}
          action={
            <ButtonLink href="/settings" variant="primary">
              Mở Cài đặt
            </ButtonLink>
          }
        />
      )}

      {items.length > 0 && (
        <Card padded={false} className="relative overflow-x-auto">
          <table className="w-full min-w-[960px] text-sm">
            <thead>
              <tr className="border-b border-rule">
                <th className={`${TH} w-12`}>#</th>
                <th className={TH}>Keyword</th>
                <th className={TH}>Điểm</th>
                <th className={TH}>Cạnh tranh</th>
                <th className={TH}>Tăng trưởng</th>
                <th className={TH}>Nguồn</th>
                <th className={TH}>30 ngày</th>
                <th className={TH}>
                  <span className="sr-only">Thao tác</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={item.keyword_id} className="border-b border-rule last:border-0 hover:bg-paper/60">
                  <td className={`${TD} font-mono text-xs text-ink-2`}>{index + 1}</td>
                  <td className={TD}>
                    <Link
                      href={`/trends/${item.keyword_id}`}
                      className="whitespace-nowrap font-semibold text-ink underline-offset-2 hover:underline"
                    >
                      {item.keyword}
                    </Link>
                    <span className="mt-0.5 flex items-center gap-2 text-xs text-ink-2">
                      {item.is_new && (
                        <span className="inline-flex items-center gap-1 font-medium text-ink">
                          <span aria-hidden="true" className="size-1.5 rounded-full bg-cyan" />
                          Mới
                        </span>
                      )}
                      <span>{item.is_seed ? "seed" : "khám phá"}</span>
                      <span aria-hidden="true">·</span>
                      <Link
                        href={`/niche?keyword=${encodeURIComponent(item.keyword)}`}
                        className="whitespace-nowrap text-ink underline-offset-2 hover:underline"
                      >
                        Phân tích ngách
                      </Link>
                    </span>
                  </td>
                  <td className={TD}>
                    <HalftoneMeter value={item.score / 100} size="sm" label={String(Math.round(item.score))} />
                    {item.opportunity !== undefined && item.opportunity !== null && (
                      <span className="mt-0.5 block font-mono text-xs text-ink-2" title="Cơ hội = nhu cầu + đà tăng, trừ cạnh tranh">
                        Cơ hội {Math.round(item.opportunity)}
                      </span>
                    )}
                  </td>
                  <td className={TD}>
                    {item.listing_count !== undefined && item.listing_count !== null ? (
                      <span className="inline-flex items-center gap-2 whitespace-nowrap">
                        <span
                          className="font-mono text-xs text-ink"
                          title={`${formatInt(item.listing_count)} listing Etsy cho “${item.keyword} shirt”`}
                        >
                          {formatNumber(item.listing_count)}
                        </span>
                        {item.competition_level && <CompetitionBadge level={item.competition_level} />}
                      </span>
                    ) : (
                      <span className="font-mono text-xs text-ink-2">—</span>
                    )}
                  </td>
                  <td className={`${TD} text-sm`}>
                    <Delta value={item.growth} />
                  </td>
                  <td className={TD}>
                    <div className="flex flex-wrap items-center gap-1">
                      {item.sources.map((s) => (
                        <SourceChip key={s} source={s} />
                      ))}
                      {item.sources_rising > 0 && (
                        <span className="font-mono text-xs text-go" title={`${item.sources_rising} nguồn đang tăng`}>
                          ▲{item.sources_rising}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className={TD}>
                    <Sparkline values={item.sparkline} />
                  </td>
                  <td className={`${TD} text-right`}>
                    <div className="flex flex-col items-end gap-1.5">
                      <WorkStatus kind="keyword" id={item.keyword_id} title={item.keyword} />
                      {!item.is_seed && (
                        <Button size="sm" variant="secondary" onClick={() => follow(item.keyword)}>
                          + Theo dõi
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
