"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import ProductCard from "@/components/ProductCard";
import { ApiError, api, type ProductPage, type TrendDetail } from "@/lib/api";
import { METRIC_LABEL, SOURCE_LABEL, formatGrowth, formatNumber } from "@/lib/format";

type Loaded = { key: string; detail?: TrendDetail; products?: ProductPage; error?: string };

function pct(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

export default function TrendDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const [tick, setTick] = useState(0);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const key = `${id}#${tick}`;
  const loading = loaded?.key !== key;

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.getTrend(id), api.listProducts({ keyword_id: id, sort: "velocity", limit: 20 })])
      .then(([detail, products]) => !cancelled && setLoaded({ key, detail, products }))
      .catch((err) =>
        !cancelled &&
        setLoaded({ key, error: err instanceof ApiError && err.status === 404 ? "Không tìm thấy keyword." : String(err) }),
      );
    return () => {
      cancelled = true;
    };
  }, [id, key]);

  async function follow(keyword: string) {
    try {
      await api.addSeed(keyword);
      setMessage("Đã thêm vào watchlist — lần quét tới sẽ lấy sản phẩm Etsy (shop US).");
      setTick((t) => t + 1);
    } catch (err) {
      setMessage(err instanceof ApiError && err.status === 409 ? "Keyword đã có trong watchlist." : String(err));
    }
  }

  if (loading) return <p className="text-sm text-zinc-500">Đang tải…</p>;
  if (loaded?.error || !loaded?.detail) return <p className="text-sm text-red-600">{loaded?.error}</p>;
  const { detail, products } = loaded;
  const trend = detail.trend;

  return (
    <div className="space-y-8">
      <div>
        <Link href="/" className="text-sm text-zinc-500 hover:underline">
          ← Trend Radar
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{detail.keyword}</h1>
          <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600">
            {detail.is_seed ? "seed" : "ngách khám phá"}
          </span>
          {!detail.is_pod_relevant && (
            <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">có thể không phải POD</span>
          )}
          {!detail.is_seed && (
            <button
              onClick={() => follow(detail.keyword)}
              className="rounded border border-zinc-300 px-2 py-1 text-xs hover:bg-zinc-50"
            >
              + Theo dõi
            </button>
          )}
        </div>
        {message && <p className="mt-3 rounded-md bg-zinc-100 p-3 text-sm">{message}</p>}
      </div>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {[
          ["Điểm", trend ? String(Math.round(trend.score)) : "—"],
          ["Nhu cầu", pct(trend?.demand ?? null)],
          ["Đà tăng", pct(trend?.momentum ?? null)],
          ["Cạnh tranh (tương đối)", pct(trend?.competition ?? null)],
          ["Tăng trưởng", formatGrowth(trend?.growth ?? null)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-md border border-zinc-200 bg-white p-3">
            <p className="text-xs text-zinc-500">{label}</p>
            <p className="text-lg font-semibold">{value}</p>
          </div>
        ))}
      </section>

      <section className="space-y-3">
        <h2 className="font-semibold">Tín hiệu 30 ngày (thị trường Mỹ)</h2>
        {detail.signals.length === 0 && <p className="text-sm text-zinc-500">Chưa có tín hiệu.</p>}
        <div className="grid gap-4 md:grid-cols-2">
          {detail.signals.map((series) => (
            <div key={`${series.source}/${series.metric}`} className="rounded-md border border-zinc-200 bg-white p-3">
              <p className="mb-2 text-sm font-medium">
                {SOURCE_LABEL[series.source] ?? series.source} · {METRIC_LABEL[series.metric] ?? series.metric}
              </p>
              {series.points.length < 2 ? (
                <p className="text-sm text-zinc-600">
                  {formatNumber(series.points[0]?.value ?? null)}{" "}
                  <span className="text-xs text-zinc-400">(cần ≥ 2 ngày để vẽ biểu đồ)</span>
                </p>
              ) : (
                <div className="h-40">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={series.points}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" />
                      <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 10 }} width={48} />
                      <Tooltip />
                      <Line type="monotone" dataKey="value" stroke="#ea580c" dot={false} strokeWidth={2} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="font-semibold">Keyword liên quan</h2>
        {detail.related.length === 0 && <p className="text-sm text-zinc-500">Chưa có.</p>}
        <div className="flex flex-wrap gap-2">
          {detail.related.map((r) => (
            <Link
              key={`${r.relation}-${r.keyword_id}-${r.source}`}
              href={`/trends/${r.keyword_id}`}
              className="rounded-full border border-zinc-300 bg-white px-3 py-1 text-sm hover:bg-zinc-50"
            >
              {r.relation === "parent" ? "↑ " : ""}
              {r.keyword}
              <span className="ml-1 text-xs text-zinc-400">
                {r.score !== null ? Math.round(r.score) : "—"} · {SOURCE_LABEL[r.source] ?? r.source}
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="font-semibold">Sản phẩm Etsy (shop US)</h2>
        {!detail.is_seed && (products?.items.length ?? 0) === 0 && (
          <p className="text-sm text-zinc-500">Theo dõi keyword này để lấy sản phẩm Etsy từ lần quét tới.</p>
        )}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {products?.items.map((p) => <ProductCard key={p.id} product={p} />)}
        </div>
      </section>
    </div>
  );
}
