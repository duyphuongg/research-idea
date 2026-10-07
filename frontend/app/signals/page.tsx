"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import SignalCard from "@/components/SignalCard";
import { Button, ButtonLink, EmptyState, InkDot, Notice, PageHeader, Select, Tabs } from "@/components/ui";
import { api, type SignalPage, type SignalQuery, type SignalSort } from "@/lib/api";

const PAGE_SIZE = 60;

const TABS: { value: NonNullable<SignalQuery["status"]>; label: string }[] = [
  { value: "signals", label: "Tất cả tín hiệu" },
  { value: "super_breakout", label: "Super Breakout" },
  { value: "steady_grower", label: "Steady Grower" },
  { value: "graduated", label: "Graduated" },
  { value: "calibrating", label: "Calibrating" },
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

export default function SignalsPage() {
  return (
    <Suspense fallback={null}>
      <SignalsView />
    </Suspense>
  );
}

const STATUS_VALUES = TABS.map((t) => t.value);

function SignalsView() {
  const params = useSearchParams();
  const paramStatus = STATUS_VALUES.find((v) => v === params.get("status"));
  const [query, setQuery] = useState<SignalQuery>({
    status: paramStatus ?? "signals",
    keyword: params.get("keyword")?.trim() || undefined,
    sort: "delta_saves",
    limit: PAGE_SIZE,
    offset: 0,
  });
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

  const updatedOn = result?.data?.updated_on;
  const tabs = TABS.map((t) => ({ value: t.value, label: t.label, count: tabCount(t.value) }));

  return (
    <div>
      <PageHeader
        eyebrow={<>Listing Signals{updatedOn && <span className="font-mono">· {updatedOn}</span>}</>}
        title="Etsy bứt phá"
        description="Mẫu áo mới (≤ 30 ngày) của shop ở Mỹ đang tăng lượt xem / lượt lưu nhanh."
        actions={
          <>
            <Select
              size="md"
              aria-label="Tuổi listing"
              value={query.max_age ?? ""}
              onChange={(e) => update({ max_age: e.target.value ? Number(e.target.value) : undefined })}
            >
              {AGES.map((a) => (
                <option key={a.label} value={a.value ?? ""}>
                  {a.label}
                </option>
              ))}
            </Select>
            <Select aria-label="Sắp xếp" value={query.sort} onChange={(e) => update({ sort: e.target.value as SignalSort })}>
              {SORTS.map((s) => (
                <option key={s.value} value={s.value}>
                  Sắp xếp: {s.label}
                </option>
              ))}
            </Select>
          </>
        }
      />

      <Tabs
        label="Trạng thái tín hiệu"
        items={tabs}
        value={query.status ?? "signals"}
        onChange={(v) => update({ status: v })}
        className="mb-3"
      />
      {query.keyword && (
        <p className="mb-3 flex flex-wrap items-center gap-2 text-sm text-ink">
          <span className="text-ink-2">Lọc theo keyword:</span>
          <span className="font-medium">{query.keyword}</span>
          <Button size="sm" variant="ghost" onClick={() => update({ keyword: undefined })}>
            Bỏ lọc
          </Button>
        </p>
      )}
      <p className="mb-5 flex items-start gap-2 text-xs leading-5 text-ink-2">
        <InkDot ink="cyan" size={7} className="mt-1.5" />
        <span>
          Listing áo mới (≤ 30 ngày) của shop ở Mỹ, cập nhật hằng ngày. Lượt lưu = favorites; DSR = lượt lưu mới / lượt
          xem mới. Cần ≥ 2 lần quét để có tín hiệu. Lượt xem / lượt lưu là chỉ số ước tính (proxy), không phải doanh số
          thật.
        </span>
      </p>

      {result?.error && !loading && (
        <Notice tone="error" title="Không tải được dữ liệu" className="mb-4">
          <span className="break-all font-mono text-xs">{result.error}</span>
        </Notice>
      )}
      {loading && <p className="py-6 text-sm text-ink-2">Đang tải…</p>}
      {!loading && result?.data && result.data.items.length === 0 &&
        (result.data.updated_on ? (
          <EmptyState
            title={
              <>
                Đang hiệu chỉnh <span className="font-mono">{counts?.calibrating ?? 0}</span> listing
              </>
            }
            body="Tín hiệu xuất hiện sau lần quét ngày mai — cần ít nhất 2 lần quét để tính mức tăng mỗi ngày."
            action={
              query.status !== "calibrating" ? (
                <Button variant="secondary" size="sm" onClick={() => update({ status: "calibrating" })}>
                  Xem tab Calibrating
                </Button>
              ) : undefined
            }
          />
        ) : (
          <EmptyState
            title="Chưa có dữ liệu"
            body="Bấm “Quét ngay” trong Cài đặt; tín hiệu xuất hiện sau 2 ngày quét."
            action={
              <ButtonLink href="/settings" variant="primary" size="sm">
                Mở Cài đặt
              </ButtonLink>
            }
          />
        ))}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-4 xl:grid-cols-5">
        {result?.data?.items.map((item) => <SignalCard key={item.product_id} item={item} />)}
      </div>

      {total > PAGE_SIZE && (
        <Pager
          offset={offset}
          total={total}
          pageSize={PAGE_SIZE}
          onPrev={() => setQuery((q) => ({ ...q, offset: Math.max(0, offset - PAGE_SIZE) }))}
          onNext={() => setQuery((q) => ({ ...q, offset: offset + PAGE_SIZE }))}
        />
      )}
    </div>
  );
}

function Pager({
  offset,
  total,
  pageSize,
  onPrev,
  onNext,
}: {
  offset: number;
  total: number;
  pageSize: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  return (
    <nav aria-label="Phân trang" className="mt-8 flex items-center justify-center gap-4 text-sm">
      <Button size="sm" disabled={offset === 0} onClick={onPrev}>
        ← Trước
      </Button>
      <span className="font-mono text-xs text-ink-2">
        {offset + 1}–{Math.min(offset + pageSize, total)} / {total}
      </span>
      <Button size="sm" disabled={offset + pageSize >= total} onClick={onNext}>
        Sau →
      </Button>
    </nav>
  );
}
