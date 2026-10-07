"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import SourceHealthBanner from "@/components/SourceHealthBanner";
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

const selectClass = "rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm";

// Stale = older than yesterday (local date), so a normal daily scan never warns.
function isStale(date: string): boolean {
  const d = new Date();
  d.setDate(d.getDate() - 1);
  const pad = (n: number) => String(n).padStart(2, "0");
  const yesterday = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  return date < yesterday;
}

function RankChange({ change, isNew }: { change: number | null; isNew: boolean }) {
  if (isNew) return <span className="rounded bg-blue-100 px-1.5 py-0.5 text-xs font-semibold text-blue-700">Mới</span>;
  if (change === null || change === 0) return <span className="text-zinc-400">—</span>;
  return change > 0 ? (
    <span className="font-medium text-green-600">▲{change}</span>
  ) : (
    <span className="font-medium text-red-600">▼{Math.abs(change)}</span>
  );
}

export default function AmazonPageView() {
  const [category, setCategory] = useState("women_tshirts");
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

  return (
    <div>
      <SourceHealthBanner />
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-xl font-semibold">Amazon</h1>
        <select className={selectClass} value={category} onChange={(e) => setCategory(e.target.value)}>
          {categoryKeys.map((k) => (
            <option key={k} value={k}>
              {CATEGORY_LABEL[k] ?? k}
            </option>
          ))}
        </select>
        <div className="flex overflow-hidden rounded-md border border-zinc-300 text-sm">
          {LISTS.map((l) => (
            <button
              key={l.value}
              onClick={() => setList(l.value)}
              className={`px-3 py-1.5 ${list === l.value ? "bg-zinc-900 text-white" : "bg-white text-zinc-700 hover:bg-zinc-100"}`}
            >
              {l.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-sm">
          <input type="checkbox" checked={hideLicensed} onChange={(e) => setHideLicensed(e.target.checked)} />
          Ẩn sản phẩm có bản quyền
        </label>
      </div>
      <p className="mb-4 text-xs text-zinc-500">
        Dữ liệu từ trang Best Sellers / New Releases công khai của Amazon (Mỹ), cập nhật mỗi lần quét. Hạng là trong
        danh mục, không phải doanh số.
      </p>

      {!loading && result?.data?.date && (
        <p className="mb-3 text-sm text-zinc-600">
          Cập nhật: {result.data.date}
          {isStale(result.data.date) && (
            <span className="ml-2 rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">
              ⚠️ Dữ liệu đã cũ — lần quét gần nhất có thể bị chặn hoặc lỗi.
            </span>
          )}
        </p>
      )}

      {result?.error && !loading && <p className="text-sm text-red-600">Không tải được dữ liệu: {result.error}</p>}
      {loading && <p className="text-sm text-zinc-500">Đang tải…</p>}
      {!loading && result?.data && result.data.items.length === 0 && (
        <p className="text-sm text-zinc-500">
          Chưa có dữ liệu Amazon (có thể bị chặn hoặc chưa quét). Xem tình trạng nguồn trong{" "}
          <Link href="/settings" className="underline">Cài đặt</Link> rồi bấm &quot;Quét ngay&quot;.
        </p>
      )}

      {!loading && result?.data && result.data.items.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 text-left text-xs text-zinc-500">
              <tr>
                <th className="px-3 py-2">Hạng</th>
                <th className="px-3 py-2">Đổi</th>
                <th className="px-3 py-2">Ảnh</th>
                <th className="px-3 py-2">Sản phẩm</th>
                <th className="px-3 py-2">Đánh giá</th>
                <th className="px-3 py-2">Reviews</th>
              </tr>
            </thead>
            <tbody>
              {result.data.items.map((it) => (
                <tr key={it.product_id} className="border-t border-zinc-100">
                  <td className="px-3 py-2 font-semibold">#{it.rank}</td>
                  <td className="px-3 py-2">
                    <RankChange change={it.rank_change} isNew={it.is_new_entry} />
                  </td>
                  <td className="px-3 py-2">
                    {it.image_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={it.image_url} alt={it.title} className="h-14 w-14 rounded object-cover" loading="lazy" />
                    ) : (
                      <div className="h-14 w-14 rounded bg-zinc-100" />
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <a href={it.url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                      {it.title}
                    </a>
                    {it.licensed && (
                      <p className="mt-1 text-xs text-amber-700">⚠️ Có thể có bản quyền — đừng sao chép</p>
                    )}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">{it.rating !== null ? `★ ${it.rating}` : "—"}</td>
                  <td className="px-3 py-2">{it.reviews !== null ? formatNumber(it.reviews) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
