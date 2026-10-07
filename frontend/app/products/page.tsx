"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import ProductCard from "@/components/ProductCard";
import SourceHealthBanner from "@/components/SourceHealthBanner";
import { Button, ButtonLink, Checkbox, EmptyState, Notice, PageHeader, Select } from "@/components/ui";
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

export default function ProductsPage() {
  return (
    <Suspense fallback={null}>
      <ProductsView />
    </Suspense>
  );
}

function ProductsView() {
  const params = useSearchParams();
  const paramKeywordId = Number(params.get("keyword_id"));
  const [query, setQuery] = useState<ProductQuery>({
    sort: "velocity",
    limit: PAGE_SIZE,
    offset: 0,
    keyword_id: Number.isInteger(paramKeywordId) && paramKeywordId > 0 ? paramKeywordId : undefined,
  });
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
      <PageHeader
        eyebrow={
          <>
            Bán chạy
            {result?.data && <span className="font-mono">· {total} sản phẩm</span>}
          </>
        }
        title="Best Sellers"
        description="Sản phẩm bán chạy theo keyword trên Etsy và Amazon, xếp theo mức tăng gần đây."
      />

      <div className="mb-3 grid grid-cols-2 items-end gap-3 rounded-md max-sm:[&_select]:w-full sm:flex sm:flex-wrap border border-rule bg-sheet p-3 shadow-card">
        <Select label="Nguồn" value={query.source ?? ""} onChange={(e) => update({ source: e.target.value || undefined })}>
          <option value="">Tất cả nguồn</option>
          <option value="etsy">Etsy</option>
          <option value="amazon">Amazon</option>
        </Select>
        <Select
          label="Loại áo"
          value={query.type ?? ""}
          onChange={(e) => update({ type: (e.target.value || undefined) as ProductType | undefined })}
        >
          {TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </Select>
        <Select
          label="Keyword"
          className="sm:max-w-[220px]"
          value={query.keyword_id ?? ""}
          onChange={(e) => update({ keyword_id: e.target.value ? Number(e.target.value) : undefined })}
        >
          <option value="">Tất cả keyword</option>
          {seeds.map((s) => (
            <option key={s.id} value={s.keyword_id}>
              {s.keyword}
            </option>
          ))}
        </Select>
        <Select label="Sắp xếp" value={query.sort} onChange={(e) => update({ sort: e.target.value as ProductSort })}>
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </Select>
        <Checkbox
          className="col-span-2 h-9 sm:ml-auto"
          label="Ẩn sản phẩm có bản quyền"
          checked={query.hide_licensed ?? false}
          onChange={(e) => update({ hide_licensed: e.target.checked || undefined })}
        />
      </div>
      <p className="mb-5 text-xs leading-5 text-ink-2">
        Lượt xem / favorites / reviews và mức tăng 7 ngày là chỉ số ước tính (proxy), không phải doanh số thật. Chỉ
        hiển thị shop ở Mỹ. 🔥 = top 10% tăng trưởng trong cùng nguồn và loại áo.
      </p>

      {result?.error && !loading && (
        <Notice tone="error" title="Không tải được dữ liệu" className="mb-4">
          <span className="break-all font-mono text-xs">{result.error}</span>
        </Notice>
      )}
      {loading && <p className="py-6 text-sm text-ink-2">Đang tải…</p>}
      {!loading && result?.data && result.data.items.length === 0 && (
        <EmptyState
          title="Chưa có sản phẩm"
          body={<>Thêm keyword trong <Link href="/settings" className="underline">Cài đặt</Link> rồi bấm &quot;Quét ngay&quot;.</>}
          action={
            <ButtonLink href="/settings" variant="primary" size="sm">
              Mở Cài đặt
            </ButtonLink>
          }
        />
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-4 xl:grid-cols-5">
        {result?.data?.items.map((p) => <ProductCard key={p.id} product={p} />)}
      </div>

      {total > PAGE_SIZE && (
        <nav aria-label="Phân trang" className="mt-8 flex items-center justify-center gap-4 text-sm">
          <Button
            size="sm"
            disabled={offset === 0}
            onClick={() => setQuery((q) => ({ ...q, offset: Math.max(0, offset - PAGE_SIZE) }))}
          >
            ← Trước
          </Button>
          <span className="font-mono text-xs text-ink-2">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} / {total}
          </span>
          <Button
            size="sm"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setQuery((q) => ({ ...q, offset: offset + PAGE_SIZE }))}
          >
            Sau →
          </Button>
        </nav>
      )}
    </div>
  );
}
