"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Sparkline from "@/components/Sparkline";
import SourceHealthBanner from "@/components/SourceHealthBanner";
import { ApiError, api, type TrendPage, type TrendQuery } from "@/lib/api";
import { SOURCE_LABEL, formatGrowth } from "@/lib/format";

type Result = { key: string; data?: TrendPage; error?: string };

const selectClass = "rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm";

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

  return (
    <div>
      <SourceHealthBanner />
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-xl font-semibold">Trend Radar</h1>
        <select
          className={selectClass}
          value={query.source ?? ""}
          onChange={(e) => setQuery((q) => ({ ...q, source: e.target.value || undefined }))}
        >
          <option value="">Tất cả nguồn</option>
          {Object.entries(SOURCE_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          className={selectClass}
          value={query.origin ?? ""}
          onChange={(e) =>
            setQuery((q) => ({ ...q, origin: (e.target.value || undefined) as TrendQuery["origin"] }))
          }
        >
          <option value="">Seed + khám phá</option>
          <option value="seed">Chỉ seed</option>
          <option value="discovered">Chỉ ngách khám phá</option>
        </select>
        <label className="flex items-center gap-1 text-sm">
          <input
            type="checkbox"
            checked={query.pod_only ?? true}
            onChange={(e) => setQuery((q) => ({ ...q, pod_only: e.target.checked }))}
          />
          Chỉ POD
        </label>
      </div>
      <p className="mb-4 text-xs text-zinc-500">
        Điểm 0–100 = nhu cầu (35%) + đà tăng (45%) + ít cạnh tranh (20%), tính trên dữ liệu thị trường Mỹ: Etsy (chỉ shop
        US), Google gợi ý (US), Google xu hướng ngày (US). Đà tăng cần ≥ 8 ngày dữ liệu.
        {result?.data?.date && <> Cập nhật: {result.data.date}.</>}
      </p>
      {message && <p className="mb-3 rounded-md bg-zinc-100 p-3 text-sm">{message}</p>}
      {result?.error && !loading && <p className="text-sm text-red-600">Không tải được dữ liệu: {result.error}</p>}
      {loading && <p className="text-sm text-zinc-500">Đang tải…</p>}
      {!loading && result?.data && items.length === 0 && (
        <p className="text-sm text-zinc-500">
          Chưa có điểm. Thêm keyword trong <Link href="/settings" className="underline">Cài đặt</Link> rồi bấm &quot;Quét ngay&quot;.
        </p>
      )}

      {items.length > 0 && (
        <table className="w-full rounded-md border border-zinc-200 bg-white text-left text-sm">
          <thead className="bg-zinc-50 text-xs uppercase text-zinc-500">
            <tr>
              <th className="px-3 py-2">#</th>
              <th className="px-3 py-2">Keyword</th>
              <th className="px-3 py-2">Điểm</th>
              <th className="px-3 py-2">Tăng trưởng</th>
              <th className="px-3 py-2">Nguồn</th>
              <th className="px-3 py-2">30 ngày</th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-200">
            {items.map((item, index) => (
              <tr key={item.keyword_id}>
                <td className="px-3 py-2 text-zinc-400">{index + 1}</td>
                <td className="px-3 py-2">
                  <Link href={`/trends/${item.keyword_id}`} className="font-medium hover:underline">
                    {item.keyword}
                  </Link>
                  {item.is_new && <span className="ml-2 rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-800">Mới</span>}
                  <span className="ml-2 text-xs text-zinc-400">{item.is_seed ? "seed" : "khám phá"}</span>
                </td>
                <td className="px-3 py-2 font-semibold">{Math.round(item.score)}</td>
                <td className={`px-3 py-2 ${item.growth !== null && item.growth > 0 ? "text-green-700" : "text-zinc-500"}`}>
                  {formatGrowth(item.growth)}
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-1">
                    {item.sources.map((s) => (
                      <span key={s} className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-600">
                        {SOURCE_LABEL[s] ?? s}
                      </span>
                    ))}
                    {item.sources_rising > 0 && <span className="text-xs text-green-700">↑{item.sources_rising}</span>}
                  </div>
                </td>
                <td className="px-3 py-2">
                  <Sparkline values={item.sparkline} />
                </td>
                <td className="px-3 py-2 text-right">
                  {!item.is_seed && (
                    <button
                      onClick={() => follow(item.keyword)}
                      className="rounded border border-zinc-300 px-2 py-1 text-xs hover:bg-zinc-50"
                    >
                      + Theo dõi
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
