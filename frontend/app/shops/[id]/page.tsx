"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import ProductCard from "@/components/ProductCard";
import { SalesDelta, ShopIcon, WatchToggle, formatRating, formatSpl } from "@/components/ShopBits";
import { Card, EmptyState, Notice, PageHeader, Section } from "@/components/ui";
import { ApiError, api, type ShopDetail } from "@/lib/api";
import { formatInt } from "@/lib/format";

type Loaded = { id: number; detail?: ShopDetail; error?: string };

/** Hex values of the Press Room inks (app/globals.css @theme) — Recharts needs raw colours. */
const INK_HEX = "#15171E";
const RULE_HEX = "#D5DAE1";
const INK2_HEX = "#5B6170";
const AXIS_TICK = { fontSize: 10, fill: INK2_HEX, fontFamily: "var(--font-plex-mono), ui-monospace, monospace" };

function StatBlock({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-2 bg-sheet p-4">
      <p className="eyebrow text-ink-2">{label}</p>
      <p className="font-mono text-[26px] font-medium leading-none text-ink sm:text-[32px]">{value}</p>
    </div>
  );
}

export default function ShopDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const loading = loaded?.id !== id;

  useEffect(() => {
    let cancelled = false;
    api
      .getShop(id)
      .then((detail) => !cancelled && setLoaded({ id, detail }))
      .catch(
        (err) =>
          !cancelled &&
          setLoaded({ id, error: err instanceof ApiError && err.status === 404 ? "Không tìm thấy shop." : String(err) }),
      );
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function toggleWatch(detail: ShopDetail) {
    setBusy(true);
    setMessage(null);
    try {
      const updated = detail.watched ? await api.unwatchShop(detail.id) : await api.watchShop(detail.id);
      setLoaded({ id, detail: { ...detail, ...updated } });
    } catch (err) {
      setMessage(String(err));
    } finally {
      setBusy(false);
    }
  }

  if (loading)
    return (
      <Card className="text-sm text-ink-2" role="status">
        Đang tải…
      </Card>
    );
  if (loaded?.error || !loaded?.detail)
    return (
      <div className="space-y-4">
        <Link href="/shops" className="text-sm text-ink-2 hover:text-ink hover:underline">
          ← Shop Explorer
        </Link>
        <Notice tone="error" title="Không tải được shop">
          {loaded?.error}
        </Notice>
      </div>
    );
  const shop = loaded.detail;
  const points = shop.series.filter((p) => p.sold_count !== null);

  return (
    <div className="space-y-8">
      <div>
        <Link href="/shops" className="mb-3 inline-block text-sm text-ink-2 hover:text-ink hover:underline">
          ← Shop Explorer
        </Link>
        <PageHeader
          eyebrow={
            <>
              Shop Explorer<span className="font-mono">· {shop.last_seen}</span>
            </>
          }
          title={
            <span className="flex min-w-0 items-center gap-3">
              <ShopIcon shop={shop} size={44} />
              <span className="min-w-0 break-words">{shop.name}</span>
            </span>
          }
          description={
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span>
                Mở năm <span className="font-mono text-ink">{shop.opened_year ?? "—"}</span>
              </span>
              <span>
                <span className="font-mono text-ink">{formatInt(shop.listing_count)}</span> listing
              </span>
              <span className="font-mono text-ink">{formatRating(shop.review_average, shop.review_count)}</span>
              {shop.url && (
                <a
                  href={shop.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-ink underline underline-offset-2"
                >
                  Etsy ↗
                </a>
              )}
            </span>
          }
          actions={<WatchToggle shop={shop} busy={busy} onToggle={() => toggleWatch(shop)} withLabel />}
        />
        {message && (
          <Notice tone="error">
            <span className="break-all font-mono text-xs">{message}</span>
          </Notice>
        )}
      </div>

      <section aria-label="Thông số" className="overflow-hidden rounded-md border border-rule shadow-card">
        <div className="grid grid-cols-2 gap-px bg-rule sm:grid-cols-3 lg:grid-cols-5">
          <StatBlock label="Tổng đơn" value={formatInt(shop.sold_count)} />
          <StatBlock label="+7 ngày" value={<SalesDelta delta={shop.sales_7d} window={7} />} />
          <StatBlock label="+30 ngày" value={<SalesDelta delta={shop.sales_30d} window={30} />} />
          <StatBlock label="Đơn/listing" value={formatSpl(shop.sales_per_listing)} />
          <StatBlock label="+Yêu thích 7 ngày" value={<SalesDelta delta={shop.favorers_7d} window={7} />} />
          <div className="bg-sheet lg:hidden" aria-hidden="true" />
        </div>
      </section>

      <Section title="Tổng đơn theo ngày">
        <Card>
          {points.length < 2 ? (
            <p className="flex flex-wrap items-baseline gap-2">
              <span className="font-mono text-2xl text-ink">{formatInt(points[0]?.sold_count ?? shop.sold_count)}</span>
              <span className="text-xs text-ink-2">(cần ≥ 2 ngày để vẽ biểu đồ)</span>
            </p>
          ) : (
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={points} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke={RULE_HEX} strokeDasharray="2 4" vertical={false} />
                  <XAxis dataKey="date" tick={AXIS_TICK} tickLine={false} axisLine={{ stroke: RULE_HEX }} />
                  <YAxis
                    tick={AXIS_TICK}
                    width={56}
                    tickLine={false}
                    axisLine={false}
                    domain={["dataMin", "dataMax"]}
                    tickFormatter={(v) => formatInt(Number(v))}
                  />
                  <Tooltip
                    contentStyle={{ border: `1px solid ${RULE_HEX}`, borderRadius: 6, fontSize: 12 }}
                    labelStyle={{ color: INK2_HEX }}
                    formatter={(v) => [formatInt(Number(v)), "Tổng đơn"]}
                  />
                  <Line type="linear" dataKey="sold_count" stroke={INK_HEX} dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </Section>

      <Section title="Sản phẩm của shop app đã thấy">
        {shop.products.length === 0 ? (
          <EmptyState title="Chưa có sản phẩm" body="App chưa lưu listing nào của shop này." />
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-4 xl:grid-cols-5">
            {shop.products.map((p) => (
              <ProductCard key={p.id} product={p} />
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}
