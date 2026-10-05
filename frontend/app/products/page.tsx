"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import ProductCard from "@/components/ProductCard";
import SourceHealthBanner from "@/components/SourceHealthBanner";
import { api, type ProductPage, type ProductQuery, type ProductSort, type ProductType, type Seed } from "@/lib/api";

const PAGE_SIZE = 60;

const SORTS: { value: ProductSort; label: string }[] = [
  { value: "velocity", label: "Tăng trưởng 7 ngày" },
  { value: "reviews", label: "Phổ biến (reviews/lượt xem)" },
  { value: "newest", label: "Mới đăng" },
  { value: "price", label: "Giá thấp → cao" },
];

const TYPES: { value: ProductType | ""; label: string }[] = [
  { value: "", label: "Tất cả loại" },
  { value: "tshirt", label: "T-shirt" },
  { value: "sweatshirt", label: "Sweatshirt" },
  { value: "hoodie", label: "Hoodie" },
];

type Result = { key: string; data?: ProductPage; error?: string };

const selectClass = "rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm";

export default function ProductsPage() {
  const [query, setQuery] = useState<ProductQuery>({ sort: "velocity", limit: PAGE_SIZE, offset: 0 });
  const [result, setResult] = useState<Result | null>(null);
  const [seeds, setSeeds] = useState<Seed[]>([]);
  const key = JSON.stringify(query);
  const loading = result?.key !== key;

  useEffect(() => {
    api.listSeeds().then(setSeeds).catch(() => setSeeds([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .listProducts(query)
      .then((data) => !cancelled && setResult({ key, data }))
      .catch((err) => !cancelled && setResult({ key, error: String(err) }));
    return () => {
      cancelled = true;
    };
  }, [key, query]);

  const update = (patch: Partial<ProductQuery>) => setQuery((q) => ({ ...q, offset: 0, ...patch }));
  const offset = query.offset ?? 0;
  const total = result?.data?.total ?? 0;

  return (
    <div>
      <SourceHealthBanner />
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-xl font-semibold">Best Sellers</h1>
        <select className={selectClass} value={query.source ?? ""} onChange={(e) => update({ source: e.target.value || undefined })}>
          <option value="">Tất cả nguồn</option>
          <option value="etsy">Etsy</option>
        </select>
        <select
          className={selectClass}
          value={query.type ?? ""}
          onChange={(e) => update({ type: (e.target.value || undefined) as ProductType | undefined })}
        >
          {TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
        <select
          className={selectClass}
          value={query.keyword_id ?? ""}
          onChange={(e) => update({ keyword_id: e.target.value ? Number(e.target.value) : undefined })}
        >
          <option value="">Tất cả keyword</option>
          {seeds.map((s) => (
            <option key={s.id} value={s.keyword_id}>
              {s.keyword}
            </option>
          ))}
        </select>
        <select className={selectClass} value={query.sort} onChange={(e) => update({ sort: e.target.value as ProductSort })}>
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </div>
      <p className="mb-4 text-xs text-zinc-500">
        Lượt xem / favorites / reviews và mức tăng 7 ngày là chỉ số ước tính (proxy), không phải doanh số thật. Chỉ
        hiển thị shop ở Mỹ. 🔥 = top 10% tăng trưởng trong cùng nguồn và loại áo.
      </p>

      {result?.error && !loading && <p className="text-sm text-red-600">Không tải được dữ liệu: {result.error}</p>}
      {loading && <p className="text-sm text-zinc-500">Đang tải…</p>}
      {!loading && result?.data && result.data.items.length === 0 && (
        <p className="text-sm text-zinc-500">
          Chưa có sản phẩm. Thêm keyword trong <Link href="/settings" className="underline">Cài đặt</Link> rồi bấm &quot;Quét ngay&quot;.
        </p>
      )}

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {result?.data?.items.map((p) => <ProductCard key={p.id} product={p} />)}
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
