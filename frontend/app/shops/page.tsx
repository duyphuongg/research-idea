"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { SalesDelta, ShopIcon, WatchToggle, formatRating, formatSpl } from "@/components/ShopBits";
import { Button, Card, EmptyState, Notice, PageHeader, Select } from "@/components/ui";
import {
  api,
  type Shop,
  type ShopListings,
  type ShopOpened,
  type ShopPage,
  type ShopQuery,
  type ShopSort,
} from "@/lib/api";
import { formatInt } from "@/lib/format";

const PAGE_SIZE = 50;

const SORTS: { value: ShopSort; label: string }[] = [
  { value: "sales_7d", label: "+Đơn 7 ngày" },
  { value: "sales_30d", label: "+Đơn 30 ngày" },
  { value: "sold_count", label: "Tổng đơn" },
  { value: "sales_per_listing", label: "Đơn/listing" },
  { value: "listing_count", label: "Số listing" },
  { value: "opened_at", label: "Năm mở shop" },
  { value: "review_average", label: "Rating" },
  { value: "last_seen", label: "Mới thấy" },
];
const MIN_SALES: { value: number; label: string }[] = [
  { value: 1000, label: "≥ 1,000 đơn" },
  { value: 10000, label: "≥ 10,000 đơn" },
  { value: 50000, label: "≥ 50,000 đơn" },
  { value: 100000, label: "≥ 100,000 đơn" },
];
const LISTINGS: { value: ShopListings; label: string }[] = [
  { value: "lt200", label: "< 200 listing" },
  { value: "200_1000", label: "200–1,000 listing" },
  { value: "gt1000", label: "> 1,000 listing" },
];
const MIN_SPL: { value: number; label: string }[] = [
  { value: 5, label: "≥ 5 đơn/listing" },
  { value: 10, label: "≥ 10 đơn/listing" },
  { value: 30, label: "≥ 30 đơn/listing" },
  { value: 100, label: "≥ 100 đơn/listing" },
];
const OPENED: { value: ShopOpened; label: string }[] = [
  { value: "2026", label: "Mở năm 2026" },
  { value: "2025plus", label: "Mở từ 2025" },
  { value: "2024plus", label: "Mở từ 2024" },
  { value: "before2024", label: "Mở trước 2024" },
];
const MIN_RATING: { value: number; label: string }[] = [
  { value: 4.5, label: "★ ≥ 4.5" },
  { value: 4.8, label: "★ ≥ 4.8" },
];

/** Quick filters: each sets a fixed patch; clicking an active chip clears it. */
const CHIPS: { label: string; patch: Partial<ShopQuery> }[] = [
  { label: "Đang lên 7 ngày", patch: { sort: "sales_7d" } },
  { label: "Shop mới 2025–2026", patch: { opened: "2025plus" } },
  { label: "Ít listing bán nhiều", patch: { listings: "lt200", min_spl: 30 } },
  { label: "Shop lớn", patch: { min_sales: 50000 } },
];

const DEFAULTS: ShopQuery = { sort: "sales_7d", order: "desc" };
const FILTER_KEYS = ["q", "min_sales", "listings", "min_spl", "opened", "min_rating"] as const;
const URL_KEYS = [...FILTER_KEYS, "sort", "order"] as const;

function pick<T extends string>(value: string | null, allowed: readonly { value: T }[]): T | undefined {
  return allowed.find((a) => a.value === value)?.value;
}
function num(value: string | null): number | undefined {
  if (value === null || value.trim() === "") return undefined;
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : undefined;
}

function fromParams(params: URLSearchParams): ShopQuery {
  return {
    q: params.get("q")?.trim() || undefined,
    min_sales: num(params.get("min_sales")),
    listings: pick(params.get("listings"), LISTINGS),
    min_spl: num(params.get("min_spl")),
    opened: pick(params.get("opened"), OPENED),
    min_rating: num(params.get("min_rating")),
    sort: pick(params.get("sort"), SORTS) ?? DEFAULTS.sort,
    order: params.get("order") === "asc" ? "asc" : "desc",
    limit: PAGE_SIZE,
    offset: 0,
  };
}

/** Options for a numeric filter, keeping a value from the URL that is not in the list. */
function withCurrent(options: { value: number; label: string }[], current: number | undefined, fmt: (n: number) => string) {
  return current !== undefined && !options.some((o) => o.value === current)
    ? [...options, { value: current, label: fmt(current) }].sort((a, b) => a.value - b.value)
    : options;
}

type Result = { key: string; data?: ShopPage; error?: string };

export default function ShopsPage() {
  return (
    <Suspense fallback={null}>
      <ShopsView />
    </Suspense>
  );
}

function ShopsView() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [query, setQuery] = useState<ShopQuery>(() => fromParams(params));
  const [text, setText] = useState(query.q ?? "");
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState<Set<number>>(new Set());
  const [message, setMessage] = useState<string | null>(null);
  const key = JSON.stringify(query);
  const loading = result?.key !== key;

  // Debounce the niche search box into the query.
  useEffect(() => {
    const q = text.trim() || undefined;
    const timer = setTimeout(() => setQuery((cur) => (cur.q === q ? cur : { ...cur, q, offset: 0 })), 350);
    return () => clearTimeout(timer);
  }, [text]);

  // Filters, sort and order live in the URL (defaults omitted) so views are shareable.
  useEffect(() => {
    const next = new URLSearchParams();
    for (const k of URL_KEYS) {
      const v = query[k];
      if (v !== undefined && v !== DEFAULTS[k]) next.set(k, String(v));
    }
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }, [key, query, pathname, router]);

  useEffect(() => {
    let cancelled = false;
    api
      .listShops(query)
      .then((data) => !cancelled && setResult({ key, data }))
      .catch((err) => !cancelled && setResult({ key, error: String(err) }));
    return () => {
      cancelled = true;
    };
  }, [key, query]);

  const update = (patch: Partial<ShopQuery>) => setQuery((q) => ({ ...q, offset: 0, ...patch }));
  const chipActive = (patch: Partial<ShopQuery>) =>
    Object.entries(patch).every(([k, v]) => query[k as keyof ShopQuery] === v);
  const toggleChip = (patch: Partial<ShopQuery>) => {
    if (!chipActive(patch)) return update(patch);
    const cleared: Partial<ShopQuery> = {};
    for (const k of Object.keys(patch) as (keyof ShopQuery)[]) {
      (cleared as Record<string, unknown>)[k] = DEFAULTS[k];
    }
    // "Đang lên 7 ngày" is the default sort: clicking it again keeps it rather than clearing to itself.
    update(cleared);
  };
  const hasFilters = FILTER_KEYS.some((k) => query[k] !== undefined);
  const clearFilters = () => {
    setText("");
    update({ q: undefined, min_sales: undefined, listings: undefined, min_spl: undefined, opened: undefined, min_rating: undefined });
  };

  async function toggleWatch(shop: Shop) {
    setBusy((b) => new Set(b).add(shop.id));
    setMessage(null);
    try {
      const updated = shop.watched ? await api.unwatchShop(shop.id) : await api.watchShop(shop.id);
      setResult((r) =>
        r?.data ? { ...r, data: { ...r.data, items: r.data.items.map((s) => (s.id === updated.id ? updated : s)) } } : r,
      );
    } catch (err) {
      setMessage(String(err));
    } finally {
      setBusy((b) => {
        const next = new Set(b);
        next.delete(shop.id);
        return next;
      });
    }
  }

  const data = result?.data;
  const offset = query.offset ?? 0;
  const total = data?.total ?? 0;
  const items = data?.items ?? [];
  // History depth: the longest 7-day span any listed shop has. Below 7, the "7 ngày" numbers are partial.
  const historyDays = items.reduce((max, s) => Math.max(max, s.sales_7d?.days ?? 0), 0);

  return (
    <div>
      <PageHeader
        eyebrow={<>Shop Explorer{data?.latest_date && <span className="font-mono">· {data.latest_date}</span>}</>}
        title="Shop đang ra đơn"
        description="Shop Etsy ở Mỹ app đang thấy, xếp theo số đơn bán thêm. Số đơn tính từ tổng đơn của shop chụp mỗi ngày."
      />

      <div className="mb-3 space-y-3 rounded-md border border-rule bg-sheet p-3 shadow-card">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex min-w-0 flex-1 basis-60 flex-col gap-1">
            <span className="eyebrow text-ink-2">Ngách</span>
            <input
              type="search"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="vd: volleyball mom"
              className="h-9 w-full rounded-md border border-rule bg-sheet px-3 text-sm text-ink placeholder:text-ink-2/70 hover:border-ink-2"
            />
          </label>
          <div className="flex items-end gap-2">
            <Select label="Sắp xếp" value={query.sort} onChange={(e) => update({ sort: e.target.value as ShopSort })}>
              {SORTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </Select>
            <Button
              aria-label={query.order === "asc" ? "Đang tăng dần — đổi sang giảm dần" : "Đang giảm dần — đổi sang tăng dần"}
              onClick={() => update({ order: query.order === "asc" ? "desc" : "asc" })}
            >
              <span aria-hidden="true">{query.order === "asc" ? "↑" : "↓"}</span>
              {query.order === "asc" ? "Tăng dần" : "Giảm dần"}
            </Button>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 max-sm:[&_select]:w-full sm:flex sm:flex-wrap">
          <Select
            aria-label="Tổng đơn"
            value={query.min_sales ?? ""}
            onChange={(e) => update({ min_sales: e.target.value ? Number(e.target.value) : undefined })}
          >
            <option value="">Mọi tổng đơn</option>
            {withCurrent(MIN_SALES, query.min_sales, (n) => `≥ ${formatInt(n)} đơn`).map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          <Select
            aria-label="Số listing"
            value={query.listings ?? ""}
            onChange={(e) => update({ listings: (e.target.value || undefined) as ShopListings | undefined })}
          >
            <option value="">Mọi số listing</option>
            {LISTINGS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          <Select
            aria-label="Đơn/listing"
            value={query.min_spl ?? ""}
            onChange={(e) => update({ min_spl: e.target.value ? Number(e.target.value) : undefined })}
          >
            <option value="">Mọi đơn/listing</option>
            {withCurrent(MIN_SPL, query.min_spl, (n) => `≥ ${n} đơn/listing`).map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          <Select
            aria-label="Năm mở shop"
            value={query.opened ?? ""}
            onChange={(e) => update({ opened: (e.target.value || undefined) as ShopOpened | undefined })}
          >
            <option value="">Mọi năm mở</option>
            {OPENED.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          <Select
            aria-label="Rating"
            value={query.min_rating ?? ""}
            onChange={(e) => update({ min_rating: e.target.value ? Number(e.target.value) : undefined })}
          >
            <option value="">Mọi rating</option>
            {withCurrent(MIN_RATING, query.min_rating, (n) => `★ ≥ ${n}`).map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          {hasFilters && (
            <Button variant="ghost" onClick={clearFilters} className="max-sm:w-full">
              Bỏ lọc
            </Button>
          )}
        </div>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Lọc nhanh">
          {CHIPS.map((c) => {
            const active = chipActive(c.patch);
            return (
              <button
                key={c.label}
                type="button"
                aria-pressed={active}
                onClick={() => toggleChip(c.patch)}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                  active ? "border-ink bg-ink text-white" : "border-rule bg-sheet text-ink hover:border-ink-2"
                }`}
              >
                {c.label}
              </button>
            );
          })}
        </div>
      </div>

      {!loading && items.length > 0 && historyDays < 7 && (
        <Notice tone="info" className="mb-3">
          Số đơn 7 ngày cần đủ 7 ngày dữ liệu — hiện tính từ {historyDays} ngày.
        </Notice>
      )}
      {message && (
        <Notice tone="error" className="mb-3">
          <span className="break-all font-mono text-xs">{message}</span>
        </Notice>
      )}
      {result?.error && !loading && (
        <Notice tone="error" title="Không tải được dữ liệu" className="mb-4">
          <span className="break-all font-mono text-xs">{result.error}</span>
        </Notice>
      )}
      {loading && !data && <p className="py-6 text-sm text-ink-2">Đang tải…</p>}
      {!loading &&
        data &&
        items.length === 0 &&
        (hasFilters ? (
          <EmptyState
            title="Không có shop khớp bộ lọc"
            body="Thử bỏ bớt bộ lọc hoặc tìm ngách khác."
            action={
              <Button variant="secondary" size="sm" onClick={clearFilters}>
                Bỏ lọc
              </Button>
            }
          />
        ) : (
          <EmptyState
            title="Chưa có shop nào"
            body="Shop xuất hiện sau lần quét Etsy kế tiếp (8:00 hoặc 20:00). Số đơn 7 ngày cần vài ngày dữ liệu."
          />
        ))}

      {items.length > 0 && (
        <Card padded={false} className={`relative overflow-x-auto ${loading ? "opacity-60" : ""}`}>
          <ShopTable items={items} busy={busy} onToggle={toggleWatch} />
        </Card>
      )}

      {total > PAGE_SIZE && (
        <nav aria-label="Phân trang" className="mt-6 flex items-center justify-center gap-4 text-sm">
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

const TH_BASE = "eyebrow whitespace-nowrap px-3 py-2 font-bold text-ink-2";
const TH = `${TH_BASE} text-right`;
const TD = "whitespace-nowrap px-3 py-2 text-right font-mono text-[13px] text-ink";

function ShopTable({ items, busy, onToggle }: { items: Shop[]; busy: Set<number>; onToggle: (s: Shop) => void }) {
  return (
    <table className="w-full min-w-[880px] border-collapse text-sm">
      <thead className="border-b border-rule">
        <tr>
          <th scope="col" className={`${TH_BASE} sticky left-0 z-10 bg-sheet shadow-[1px_0_0_var(--color-rule)] text-left`}>
            Shop
          </th>
          <th scope="col" className={TH}>
            Mở năm
          </th>
          <th scope="col" className={TH}>
            Listing
          </th>
          <th scope="col" className={TH}>
            Tổng đơn
          </th>
          <th scope="col" className={`${TH} text-ink`}>
            +Đơn 7 ngày
          </th>
          <th scope="col" className={TH}>
            +Đơn 30 ngày
          </th>
          <th scope="col" className={TH}>
            Đơn/listing
          </th>
          <th scope="col" className={TH}>
            Rating
          </th>
          <th scope="col" className={`${TH_BASE} w-12 text-center`}>
            <span className="sr-only">Theo dõi</span>
          </th>
        </tr>
      </thead>
      <tbody className="divide-y divide-rule">
        {items.map((s) => (
          <tr key={s.id} className="group hover:bg-paper/50">
            <th scope="row" className="sticky left-0 z-10 bg-sheet shadow-[1px_0_0_var(--color-rule)] px-3 py-2 text-left font-normal group-hover:bg-paper">
              <span className="flex max-w-[150px] items-center sm:max-w-[260px] gap-2">
                <ShopIcon shop={s} />
                <Link href={`/shops/${s.id}`} className="truncate font-medium text-ink hover:underline">
                  {s.name}
                </Link>
                {s.url && (
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={`Mở ${s.name} trên Etsy`}
                    title="Mở trên Etsy"
                    className="shrink-0 text-xs text-ink-2 hover:text-ink"
                  >
                    ↗
                  </a>
                )}
              </span>
            </th>
            <td className={TD}>{s.opened_year ?? "—"}</td>
            <td className={TD}>{formatInt(s.listing_count)}</td>
            <td className={TD}>{formatInt(s.sold_count)}</td>
            <td className={`${TD} font-medium`}>
              <SalesDelta delta={s.sales_7d} window={7} />
            </td>
            <td className={TD}>
              <SalesDelta delta={s.sales_30d} window={30} />
            </td>
            <td className={TD}>{formatSpl(s.sales_per_listing)}</td>
            <td className={TD}>{formatRating(s.review_average)}</td>
            <td className="px-3 py-1.5 text-center">
              <WatchToggle shop={s} busy={busy.has(s.id)} onToggle={() => onToggle(s)} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
