"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import SourceHealthBanner from "@/components/SourceHealthBanner";
import { LicensedTag } from "@/components/SignalCard";
import { ButtonLink, Card, Checkbox, Delta, EmptyState, ImageZoom, InkDot, Notice, PageHeader, Select, Tabs } from "@/components/ui";
import { api, type AmazonList, type AmazonPage } from "@/lib/api";
import { formatNumber } from "@/lib/format";

const CATEGORY_LABEL: Record<string, string> = {
  women_tshirts: "Áo thun nữ",
  men_tshirts: "Áo thun nam",
  women_hoodies: "Hoodie nữ",
  women_sweatshirts: "Sweatshirt nữ",
  men_hoodies: "Hoodie nam",
  men_sweatshirts: "Sweatshirt nam",
  boys_tops: "Áo bé trai",
  girls_tops: "Áo bé gái",
};

const CATEGORY_KEYS = Object.keys(CATEGORY_LABEL);

const LISTS: { value: AmazonList; label: string }[] = [
  { value: "bestsellers", label: "Best Sellers" },
  { value: "new_releases", label: "New Releases" },
];

type Result = { key: string; data?: AmazonPage; error?: string };

// Stale = older than yesterday (local date), so a normal daily scan never warns.
function isStale(date: string): boolean {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  const pad = (n: number) => String(n).padStart(2, "0");
  const yesterday = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  return date < yesterday;
}

export default function AmazonPageView() {
  return (
    <Suspense fallback={null}>
      <AmazonView />
    </Suspense>
  );
}

function AmazonView() {
  const params = useSearchParams();
  const paramCategory = CATEGORY_KEYS.find((k) => k === params.get("category"));
  const [category, setCategory] = useState(paramCategory ?? "women_tshirts");
  const [list, setList] = useState<AmazonList>("bestsellers");
  const [hideLicensed, setHideLicensed] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const key = JSON.stringify({ category, list, hideLicensed });
  const loading = result?.key !== key;

  useEffect(() => {
    let cancelled = false;
    api
      .getAmazon({ category, list, hide_licensed: hideLicensed })
      .then((data) => !cancelled && setResult({ key, data }))
      .catch((err) => !cancelled && setResult({ key, error: String(err) }));
    return () => {
      cancelled = true;
    };
  }, [key, category, list, hideLicensed]);

  const categoryKeys = result?.data?.categories.length ? result.data.categories.map((c) => c.key) : CATEGORY_KEYS;

  const date = !loading ? result?.data?.date : null;

  return (
    <div>
      <SourceHealthBanner />
      <PageHeader
        eyebrow={<>Amazon{date && <span className="font-mono">· {date}</span>}</>}
        title="Amazon bán chạy"
        description="Top bán chạy và mới vào top theo danh mục áo trên Amazon (Mỹ)."
        actions={
          <Checkbox
            label="Ẩn sản phẩm có bản quyền"
            checked={hideLicensed}
            onChange={(e) => setHideLicensed(e.target.checked)}
          />
        }
      />

      <div className="mb-4 space-y-3">
        <div role="radiogroup" aria-label="Danh mục" className="hidden flex-wrap gap-1.5 md:flex">
          {categoryKeys.map((k) => {
            const active = k === category;
            return (
              <button
                key={k}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => setCategory(k)}
                className={`h-8 rounded-full border px-3 text-sm transition-colors ${
                  active ? "border-ink bg-ink font-medium text-white" : "border-rule bg-sheet text-ink hover:border-ink-2"
                }`}
              >
                {CATEGORY_LABEL[k] ?? k}
              </button>
            );
          })}
        </div>
        <div className="md:hidden">
          <Select label="Danh mục" value={category} onChange={(e) => setCategory(e.target.value)}>
            {categoryKeys.map((k) => (
              <option key={k} value={k}>
                {CATEGORY_LABEL[k] ?? k}
              </option>
            ))}
          </Select>
        </div>
        <Tabs label="Danh sách Amazon" items={LISTS} value={list} onChange={setList} />
      </div>

      <p className="mb-4 flex items-start gap-2 text-xs leading-5 text-ink-2">
        <InkDot ink="magenta" size={7} className="mt-1.5" />
        <span>
          Dữ liệu từ trang Best Sellers / New Releases công khai của Amazon (Mỹ), cập nhật mỗi lần quét. Hạng là trong
          danh mục, không phải doanh số.
        </span>
      </p>

      {date && isStale(date) && (
        <Notice tone="warn" title="Dữ liệu đã cũ" className="mb-4">
          Bản ghi mới nhất là ngày <span className="font-mono">{date}</span> — lần quét gần nhất có thể bị chặn hoặc lỗi.
        </Notice>
      )}

      {result?.error && !loading && (
        <Notice tone="error" title="Không tải được dữ liệu" className="mb-4">
          <span className="break-all font-mono text-xs">{result.error}</span>
        </Notice>
      )}
      {loading && <p className="py-6 text-sm text-ink-2">Đang tải…</p>}
      {!loading && result?.data && result.data.items.length === 0 && (
        <EmptyState
          title="Chưa có dữ liệu Amazon"
          body={
            <>
              Có thể bị chặn hoặc chưa quét. Xem tình trạng nguồn trong{" "}
              <Link href="/settings" className="underline">Cài đặt</Link> rồi bấm &quot;Quét ngay&quot;.
            </>
          }
          action={
            <ButtonLink href="/settings" variant="primary" size="sm">
              Mở Cài đặt
            </ButtonLink>
          }
        />
      )}

      {!loading && result?.data && result.data.items.length > 0 && (
        <Card padded={false}>
          <ol className="divide-y divide-rule">
            {result.data.items.map((it) => (
              <li key={it.product_id} className="flex items-start gap-3 px-3 py-3 sm:gap-4 sm:px-4">
                <div className="flex w-12 shrink-0 flex-col items-end gap-1 pt-0.5 sm:w-14">
                  <span className="font-display font-wide text-[28px] font-extrabold leading-none tracking-tight text-ink">
                    <span className="sr-only">Hạng </span>
                    {it.rank}
                  </span>
                  {!it.is_new_entry && it.rank_change !== null && <Delta value={it.rank_change} unit="" ratio={false} className="text-xs" />}
                </div>
                {it.image_url ? (
                  <ImageZoom src={it.image_url} alt={it.title} href={it.url} className="size-14 shrink-0 sm:size-16">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={it.image_url}
                      alt={it.title}
                      className="size-full rounded-md border border-rule bg-paper object-cover transition-colors hover:border-ink-2"
                      loading="lazy"
                    />
                  </ImageZoom>
                ) : (
                  <div className="size-14 shrink-0 rounded-md border border-rule bg-paper sm:size-16" />
                )}
                <div className="min-w-0 flex-1 space-y-1.5">
                  <a
                    href={it.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="line-clamp-2 text-sm font-medium leading-5 text-ink hover:underline"
                  >
                    {it.title}
                  </a>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs">
                    <span className="font-mono text-ink">
                      {it.rating !== null ? `★ ${it.rating}` : "★ —"}
                      <span className="text-ink-2"> · {it.reviews !== null ? formatNumber(it.reviews) : "—"} reviews</span>
                    </span>
                    <span className="hidden font-mono text-ink-2 sm:inline">{it.asin}</span>
                    {it.is_new_entry && (
                      <span className="inline-flex items-center gap-1 rounded-full border border-cyan/40 bg-cyan/10 px-2 py-0.5 text-[11px] font-medium leading-4 text-ink">
                        <span aria-hidden="true" className="size-1.5 rounded-full bg-cyan" />
                        Mới vào top
                      </span>
                    )}
                    {it.licensed && <LicensedTag />}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </Card>
      )}
    </div>
  );
}
