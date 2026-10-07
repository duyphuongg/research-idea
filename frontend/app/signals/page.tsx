"use client";

import { useEffect, useState } from "react";
import SignalCard from "@/components/SignalCard";
import { api, type SignalPage, type SignalQuery, type SignalSort } from "@/lib/api";

const PAGE_SIZE = 60;

const TABS: { value: NonNullable<SignalQuery["status"]>; label: string }[] = [
  { value: "signals", label: "Tất cả tín hiệu" },
  { value: "super_breakout", label: "🚀 Super Breakout" },
  { value: "steady_grower", label: "📈 Steady Grower" },
  { value: "graduated", label: "🎓 Graduated" },
  { value: "calibrating", label: "⏳ Calibrating" },
  { value: "all", label: "Tất cả" },
];

const AGES: { value: number | undefined; label: string }[] = [
  { value: undefined, label: "Mọi tuổi" },
  { value: 7, label: "≤ 7 ngày" },
  { value: 14, label: "≤ 14 ngày" },
  { value: 30, label: "≤ 30 ngày" },
];

const SORTS: { value: SignalSort; label: string }[] = [
  { value: "delta_saves", label: "Δ lượt lưu" },
  { value: "dsr", label: "DSR" },
  { value: "delta_views", label: "Δ lượt xem" },
  { value: "newest", label: "Mới nhất" },
];

type Result = { key: string; data?: SignalPage; error?: string };

const selectClass = "rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm";

export default function SignalsPage() {
  const [query, setQuery] = useState<SignalQuery>({ status: "signals", sort: "delta_saves", limit: PAGE_SIZE, offset: 0 });
  const [result, setResult] = useState<Result | null>(null);
  const key = JSON.stringify(query);
  const loading = result?.key !== key;

  useEffect(() => {
    let cancelled = false;
    api
      .listSignals(query)
      .then((data) => !cancelled && setResult({ key, data }))
      .catch((err) => !cancelled && setResult({ key, error: String(err) }));
    return () => {
      cancelled = true;
    };
  }, [key, query]);

  const update = (patch: Partial<SignalQuery>) => setQuery((q) => ({ ...q, offset: 0, ...patch }));
  const offset = query.offset ?? 0;
  const total = result?.data?.total ?? 0;
  const counts = result?.data?.counts;
  const tabCount = (value: string): number | undefined => {
    if (!counts) return undefined;
    if (value === "all") return Object.values(counts).reduce((a, b) => a + b, 0);
    if (value === "signals") return ["super_breakout", "steady_grower", "graduated"].reduce((a, s) => a + (counts[s] ?? 0), 0);
    return counts[value] ?? 0;
  };

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-xl font-semibold">Etsy Listing Signals</h1>
        {result?.data?.updated_on && (
          <span className="text-xs text-zinc-500">Cập nhật: {result.data.updated_on}</span>
        )}
        <select
          className={selectClass}
          value={query.max_age ?? ""}
          onChange={(e) => update({ max_age: e.target.value ? Number(e.target.value) : undefined })}
        >
          {AGES.map((a) => (
            <option key={a.label} value={a.value ?? ""}>
              {a.label}
            </option>
          ))}
        </select>
        <select className={selectClass} value={query.sort} onChange={(e) => update({ sort: e.target.value as SignalSort })}>
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </div>
      <p className="mb-4 text-xs text-zinc-500">
        Listing áo mới (≤ 30 ngày) của shop ở Mỹ, cập nhật hằng ngày. Lượt lưu = favorites; DSR = lượt lưu mới / lượt xem
        mới. Cần ≥ 2 lần quét để có tín hiệu.
      </p>

      <div className="mb-4 flex flex-wrap gap-2 text-sm">
        {TABS.map((t) => {
          const n = tabCount(t.value);
          const active = query.status === t.value;
          return (
            <button
              key={t.value}
              onClick={() => update({ status: t.value })}
              className={`rounded-full border px-3 py-1 ${active ? "border-zinc-900 bg-zinc-900 text-white" : "border-zinc-300 bg-white text-zinc-700 hover:bg-zinc-100"}`}
            >
              {t.label}
              {n !== undefined && ` (${n})`}
            </button>
          );
        })}
      </div>

      {result?.error && !loading && <p className="text-sm text-red-600">Không tải được dữ liệu: {result.error}</p>}
      {loading && <p className="text-sm text-zinc-500">Đang tải…</p>}
      {!loading && result?.data && result.data.items.length === 0 && (
        <p className="text-sm text-zinc-500">
          Chưa có dữ liệu — bấm “Quét ngay” trong Cài đặt; tín hiệu xuất hiện sau 2 ngày quét.
        </p>
      )}

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {result?.data?.items.map((item) => <SignalCard key={item.product_id} item={item} />)}
      </div>

      {total > PAGE_SIZE && (
        <div className="mt-6 flex items-center justify-center gap-4 text-sm">
          <button
            className="rounded border px-3 py-1 disabled:opacity-40"
            disabled={offset === 0}
            onClick={() => setQuery((q) => ({ ...q, offset: Math.max(0, offset - PAGE_SIZE) }))}
          >
            ← Trước
          </button>
          <span>
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} / {total}
          </span>
          <button
            className="rounded border px-3 py-1 disabled:opacity-40"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setQuery((q) => ({ ...q, offset: offset + PAGE_SIZE }))}
          >
            Sau →
          </button>
        </div>
      )}
    </div>
  );
}
